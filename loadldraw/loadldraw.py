# -*- coding: utf-8 -*-
"""Load LDraw GPLv2 license.

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software Foundation,
Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

"""

"""
Import LDraw

This module loads LDraw compatible files into Blender. Set the 
Options first, then call loadFromFile() function with the full 
filepath of a file to load.

Accepts .mpd, .ldr, .l3b, and .dat files.

Toby Nelson - tobymnelson@gmail.com
"""

import os
import sys
import math
import mathutils
import traceback
import glob
import bpy
import datetime
import struct
import re
import bmesh
import copy
import platform

# **************************************************************************************
# **************************************************************************************
class Options:
    """User Options"""

    # Full filepath to ldraw folder. If empty, some standard locations are attempted
    ldrawDirectory     = r""            # Full filepath to the ldraw parts library (searches some standard locations if left blank)
    instructionsLook   = True           # Set up scene to look like Lego Instruction booklets
    scale              = 0.01           # Size of the lego model to create. (0.04 is LeoCAD scale)
    useUnofficialParts = True           # Additionally searches <ldraw-dir>/unofficial/parts and /p for files
    resolution         = "Standard"     # Choose from "High", "Standard", or "Low"
    defaultColour      = "4"            # Default colour ("4" = red)
    createInstances    = True           # Multiple bricks share geometry (recommended)
    useColourScheme    = "lgeo"         # "ldraw", "alt", or "lgeo". LGEO gives the most true-to-life colours.
    numberNodes        = True           # Each node's name has a numerical prefix eg. 00001_car.dat (keeps nodes listed in a fixed order)
    removeDoubles      = True           # Remove duplicate vertices (recommended)
    smoothShading      = True           # Smooth the surface normals (recommended)
    edgeSplit          = True           # Edge split modifier (recommended if you use smoothShading)
    gaps               = True           # Introduces a tiny space between each brick
    gapWidth           = 0.01           # Width of gap between bricks (in Blender units)
    curvedWalls        = True           # Manipulate normals to make surfaces look slightly concave
    positionObjectOnGroundAtOrigin = True   # Centre the object at the origin, sitting on the z=0 plane
    flattenHierarchy   = False          # All parts are under the root object - no sub-models
    flattenGroups      = False          # All LEOCad groups are ignored - no groups

    # We have the option of including the 'LEGO' logo on each stud
    useLogoStuds       = False          # Use the studs with the 'LEGO' logo on them
    logoStudVersion    = "4"            # Which version of the logo to use ("3" (flat), "4" (rounded) or "5" (subtle rounded))
    instanceStuds      = False          # Each stud is a new Blender object (slow)

    # LSynth (http://www.holly-wood.it/lsynth/tutorial-en.html) is a collection of parts used to render string, hoses, cables etc
    useLSynthParts     = True           # LSynth is used to render string, hoses etc.
    LSynthDirectory    = r""            # Full path to the lsynth parts (Defaults to <ldrawdir>/unofficial/lsynth if left blank)
    studLogoDirectory  = r""            # Optional full path to the stud logo parts (if not found in unofficial directory)

    # Ambiguous Normals
    # Older LDraw parts (parts not yet BFC certified) have ambiguous normals.
    # We resolve this by creating double sided faces ("double") or by taking a best guess ("guess")
    resolveAmbiguousNormals = "guess"   # How to resolve ambiguous normals
    
    overwriteExistingMaterials = True   # If there's an existing material with the same name, do we overwrite it, or use it?
    overwriteExistingMeshes = True      # If there's an existing mesh with the same name, do we overwrite it, or use it?
    verbose            = 1              # 1 = Show messages while working, 0 = Only show warnings/errors
    
    addBevelModifier   = True           # Adds a bevel modifier to each part (for rounded edges)

    def meshOptionsString():
        """These options change the mesh, so if they change, a new mesh needs to be cached"""

        return "_".join([str(Options.scale),
                         str(Options.useUnofficialParts),
                         str(Options.instructionsLook),
                         str(Options.resolution), 
                         str(Options.defaultColour),
                         str(Options.createInstances), 
                         str(Options.useColourScheme), 
                         str(Options.removeDoubles),
                         str(Options.smoothShading), 
                         str(Options.gaps),
                         str(Options.gapWidth),
                         str(Options.curvedWalls),
                         str(Options.flattenHierarchy),
                         str(Options.useLogoStuds),
                         str(Options.logoStudVersion),
                         str(Options.instanceStuds),
                         str(Options.useLSynthParts),
                         str(Options.LSynthDirectory),
                         str(Options.studLogoDirectory),
                         str(Options.resolveAmbiguousNormals),
                         str(Options.addBevelModifier)])

# **************************************************************************************
# Globals
globalBrickCount = 0
globalObjectsToAdd = []         # Blender objects to add to the scene
globalMin = None
globalMax = None
globalContext = None
globalWeldDistance = 0.0005

# **************************************************************************************
def internalPrint(message):
    """Debug print with identification timestamp."""

    # Current timestamp (with milliseconds trimmed to two places)
    timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-4]

    message = "{0} [importldraw] {1}".format(timestamp, message)
    print("{0}".format(message))

    global globalContext
    if globalContext is not None:
        globalContext.report({'INFO'}, message)

# **************************************************************************************
def debugPrint(message):
    """Debug print with identification timestamp."""

    if Options.verbose > 0:
        internalPrint(message)

# **************************************************************************************
def printWarningOnce(key, message=None):
    if message is None:
        message = key

    if key not in Configure.warningSuppression:
        internalPrint("WARNING: {0}".format(message))
        Configure.warningSuppression[key] = True

        global globalContext
        if globalContext is not None:
            globalContext.report({'WARNING'}, message)

# **************************************************************************************
def printError(message):
    internalPrint("ERROR: {0}".format(message))

    global globalContext
    if globalContext is not None:
        globalContext.report({'ERROR'}, message)


# **************************************************************************************
# **************************************************************************************
class Math:
    identityMatrix = mathutils.Matrix((
            (1.0, 0.0, 0.0, 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0)
        ))
    rotationMatrix = mathutils.Matrix.Rotation(math.radians(-90), 4, 'X')
    reflectionMatrix = mathutils.Matrix((
        (1.0, 0.0, 0.0, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (0.0, 0.0, -1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0)
    ))

    def clamp01(value):
        return max(min(value, 1.0), 0.0)

    def __init__(self):
        # Rotation and scale matrices that convert LDraw coordinate space to Blender coordinate space
        Math.scaleMatrix = mathutils.Matrix((
                (Options.scale, 0.0,            0.0,            0.0),
                (0.0,           Options.scale,  0.0,            0.0),
                (0.0,           0.0,            Options.scale,  0.0),
                (0.0,           0.0,            0.0,            1.0)
            ))


# **************************************************************************************
# **************************************************************************************
class Configure:
    """Configuration.
    Attempts to find the ldraw directory (platform specific directories are searched).
    Stores the list of paths to parts libraries that we search for individual parts.
    Stores warning messages we have already seen so we don't see them again.
    """

    searchPaths = []
    warningSuppression = {}

    def __appendPath(path):
        if os.path.exists(path):
            Configure.searchPaths.append(path)

    def __setSearchPaths():
        Configure.searchPaths = []

        # Always search for parts in the 'models' folder
        Configure.__appendPath(os.path.join(Configure.ldrawInstallDirectory, "models"))

        # Search for stud logo parts
        if Options.useLogoStuds and Options.studLogoDirectory != "":
            if Options.resolution == "Low":
                Configure.__appendPath(os.path.join(Options.studLogoDirectory, "8"))
            Configure.__appendPath(Options.studLogoDirectory)

        # Search unofficial parts        
        if Options.useUnofficialParts:
            Configure.__appendPath(os.path.join(Configure.ldrawInstallDirectory, "unofficial", "parts"))

            if Options.resolution == "High":
                Configure.__appendPath(os.path.join(Configure.ldrawInstallDirectory, "unofficial", "p", "48"))
            elif Options.resolution == "Low":
                Configure.__appendPath(os.path.join(Configure.ldrawInstallDirectory, "unofficial", "p", "8"))
            Configure.__appendPath(os.path.join(Configure.ldrawInstallDirectory, "unofficial", "p"))

        # Search LSynth parts
        if Options.useLSynthParts:
            if Options.LSynthDirectory != "":
                Configure.__appendPath(Options.LSynthDirectory)
            else:
                Configure.__appendPath(os.path.join(Configure.ldrawInstallDirectory, "unofficial", "lsynth"))
            debugPrint("Use LSynth Parts requested")

        # Search official parts
        Configure.__appendPath(os.path.join(Configure.ldrawInstallDirectory, "parts"))
        if Options.resolution == "High":
            Configure.__appendPath(os.path.join(Configure.ldrawInstallDirectory, "p", "48"))
            debugPrint("High-res primitives selected")
        elif Options.resolution == "Low":
            Configure.__appendPath(os.path.join(Configure.ldrawInstallDirectory, "p", "8"))
            debugPrint("Low-res primitives selected")
        else:
            debugPrint("Standard-res primitives selected")

        Configure.__appendPath(os.path.join(Configure.ldrawInstallDirectory, "p"))

    def isWindows():
        return platform.system() == "Windows"

    def isMac():
        return platform.system() == "Darwin"

    def isLinux():
        return platform.system() == "Linux"

    def findDefaultLDrawDirectory():
        result = ""
        # Get list of possible ldraw installation directories for the platform
        if Configure.isWindows():
            ldrawPossibleDirectories = [
                                            "C:\\LDraw", 
                                            "C:\\Program Files\\LDraw", 
                                            "C:\\Program Files (x86)\\LDraw",
                                       ]
        elif Configure.isMac():
            ldrawPossibleDirectories = [ 
                                            "~/ldraw/", 
                                            "/Applications/LDraw/",
                                            "/Applications/ldraw/",
                                            "/usr/local/share/ldraw",
                                       ]
        else:   # Default to Linux if not Windows or Mac
            ldrawPossibleDirectories = [
                                            "~/LDraw",
                                            "~/ldraw",
                                            "~/.LDraw",
                                            "~/.ldraw",
                                            "/usr/local/share/ldraw",
                                       ]

        # Search possible directories
        for dir in ldrawPossibleDirectories:
            dir = os.path.expanduser(dir)
            if os.path.isfile(os.path.join(dir, "LDConfig.ldr")):
                result = dir
                break

        return result

    def setLDrawDirectory():
        if Options.ldrawDirectory == "":
            Configure.ldrawInstallDirectory = Configure.findDefaultLDrawDirectory()
        else:
            Configure.ldrawInstallDirectory = os.path.expanduser(Options.ldrawDirectory)

        debugPrint("The LDraw Parts Library path to be used is: {0}".format(Configure.ldrawInstallDirectory))
        Configure.__setSearchPaths()

    def __init__(self):
        Configure.setLDrawDirectory()


# **************************************************************************************
# **************************************************************************************
class LegoColours:
    """Parses and stores a table of colour / material definitions. Converts colour space."""

    colours = {}

    def __getValue(line, value):
        """Parses a colour value from the ldConfig.ldr file"""
        if value in line:
            n = line.index(value)
            return line[n + 1]

    def __sRGBtoRGBValue(value):
        # See https://en.wikipedia.org/wiki/SRGB#The_reverse_transformation
        if value < 0.04045:
            return value / 12.92
        return ((value + 0.055)/1.055)**2.4

    def sRGBtoLinearRGB(sRGBColour):
        # See https://en.wikipedia.org/wiki/SRGB#The_reverse_transformation
        (sr, sg, sb) = sRGBColour
        r = LegoColours.__sRGBtoRGBValue(sr)
        g = LegoColours.__sRGBtoRGBValue(sg)
        b = LegoColours.__sRGBtoRGBValue(sb)
        return (r,g,b)

    def hexDigitsToLinearRGBA(hexDigits, alpha):
        # String is "RRGGBB" format
        int_tuple = struct.unpack('BBB', bytes.fromhex(hexDigits))
        sRGB = tuple([val / 255 for val in int_tuple])
        linearRGB = LegoColours.sRGBtoLinearRGB(sRGB)
        return (linearRGB[0], linearRGB[1], linearRGB[2], alpha)

    def hexStringToLinearRGBA(hexString):
        """Convert colour hex value to RGB value."""
        # Handle direct colours
        # Direct colours are documented here: http://www.hassings.dk/l3/l3p.html
        match = re.fullmatch(r"0x0*([0-9])((?:[A-F0-9]{2}){3})", hexString)
        if match is not None:
            digit = match.group(1)
            rgb_str = match.group(2)

            interleaved = False
            if digit == "2":        # Opaque
                alpha = 1.0
            elif digit == "3":      # Transparent
                alpha = 0.5
            elif digit == "4":      # Opaque
                alpha = 1.0
                interleaved = True
            elif digit == "5":      # More Transparent
                alpha = 0.333
                interleaved = True
            elif digit == "6":      # Less transparent
                alpha = 0.666
                interleaved = True
            elif digit == "7":      # Invisible
                alpha = 0.0
                interleaved = True
            else:
                alpha = 1.0

            if interleaved:
                # Input string is six hex digits of two colours "RGBRGB".
                # This was designed to be a dithered colour.
                # Take the average of those two colours (R+R,G+G,B+B) * 0.5
                r = float(int(rgb_str[0], 16)) / 15
                g = float(int(rgb_str[1], 16)) / 15
                b = float(int(rgb_str[2], 16)) / 15
                colour1 = LegoColours.sRGBtoLinearRGB((r,g,b))
                r = float(int(rgb_str[3], 16)) / 15
                g = float(int(rgb_str[4], 16)) / 15
                b = float(int(rgb_str[5], 16)) / 15
                colour2 = LegoColours.sRGBtoLinearRGB((r,g,b))
                return (0.5 * (colour1[0] + colour2[0]),
                        0.5 * (colour1[1] + colour2[1]),
                        0.5 * (colour1[2] + colour2[2]), alpha)

            # String is "RRGGBB" format
            return LegoColours.hexDigitsToLinearRGBA(rgb_str, alpha)
        return None
    
    def __overwriteColour(index, colour):
        if index in LegoColours.colours:
            LegoColours.colours[index]["colour"] = colour

    def __readColourTable():
        """Reads the colour values from the LDConfig.ldr file. For details of the 
        Ldraw colour system see: http://www.ldraw.org/article/547"""
        if Options.useColourScheme == "alt":
            configFilename = "LDCfgalt.ldr"
        else:
            configFilename = "LDConfig.ldr"

        configFilepath = os.path.join(Configure.ldrawInstallDirectory, configFilename)

        ldconfig_lines = ""
        if os.path.exists(configFilepath):
            with open(configFilepath, "rt", encoding="utf_8") as ldconfig:
                ldconfig_lines = ldconfig.readlines()

        for line in ldconfig_lines:
            if len(line) > 3:
                if line[2:4].lower() == '!c':
                    line_split = line.split()

                    name = line_split[2]
                    code = int(line_split[4])
                    linearRGBA = LegoColours.hexDigitsToLinearRGBA(line_split[6][1:], 1.0)

                    colour = {
                        "name": name,
                        "colour": linearRGBA[0:3],
                        "alpha": linearRGBA[3],
                        "luminance": 0.0,
                        "material": "BASIC"
                    }

                    if "ALPHA" in line_split:
                        colour["alpha"] = int(LegoColours.__getValue(line_split, "ALPHA")) / 256.0

                    if "LUMINANCE" in line_split:
                        colour["luminance"] = int(LegoColours.__getValue(line_split, "LUMINANCE"))

                    if "CHROME" in line_split:
                        colour["material"] = "CHROME"

                    if "PEARLESCENT" in line_split:
                        colour["material"] = "PEARLESCENT"

                    if "RUBBER" in line_split:
                        colour["material"] = "RUBBER"

                    if "METAL" in line_split:
                        colour["material"] = "METAL"

                    if "MATERIAL" in line_split:
                        subline = line_split[line_split.index("MATERIAL"):]

                        colour["material"]         = LegoColours.__getValue(subline, "MATERIAL")
                        hexDigits                  = LegoColours.__getValue(subline, "VALUE")[1:]
                        colour["secondary_colour"] = LegoColours.hexDigitsToLinearRGBA(hexDigits, 1.0)
                        colour["fraction"]         = LegoColours.__getValue(subline, "FRACTION")
                        colour["vfraction"]        = LegoColours.__getValue(subline, "VFRACTION")
                        colour["size"]             = LegoColours.__getValue(subline, "SIZE")
                        colour["minsize"]          = LegoColours.__getValue(subline, "MINSIZE")
                        colour["maxsize"]          = LegoColours.__getValue(subline, "MAXSIZE")

                    LegoColours.colours[code] = colour

        if Options.useColourScheme == "lgeo":
            # LGEO is a parts library for rendering LEGO using the povray rendering software.
            # It has a list of LEGO colours suitable for realistic rendering.
            # I've extracted the following colours from the LGEO file: lg_color.inc
            # LGEO is downloadable from http://ldraw.org/downloads-2/downloads.html
            # We overwrite the standard LDraw colours if we have better LGEO colours.
            LegoColours.__overwriteColour(0,   ( 33/255,  33/255,  33/255))
            LegoColours.__overwriteColour(1,   ( 13/255, 105/255, 171/255))
            LegoColours.__overwriteColour(2,   ( 40/255, 127/255,  70/255))
            LegoColours.__overwriteColour(3,   (  0/255, 143/255, 155/255))
            LegoColours.__overwriteColour(4,   (196/255,  40/255,  27/255))
            LegoColours.__overwriteColour(5,   (205/255,  98/255, 152/255))
            LegoColours.__overwriteColour(6,   ( 98/255,  71/255,  50/255))
            LegoColours.__overwriteColour(7,   (161/255, 165/255, 162/255))
            LegoColours.__overwriteColour(8,   (109/255, 110/255, 108/255))
            LegoColours.__overwriteColour(9,   (180/255, 210/255, 227/255))
            LegoColours.__overwriteColour(10,  ( 75/255, 151/255,  74/255))
            LegoColours.__overwriteColour(11,  ( 85/255, 165/255, 175/255))
            LegoColours.__overwriteColour(12,  (242/255, 112/255,  94/255))
            LegoColours.__overwriteColour(13,  (252/255, 151/255, 172/255))
            LegoColours.__overwriteColour(14,  (245/255, 205/255,  47/255))
            LegoColours.__overwriteColour(15,  (242/255, 243/255, 242/255))
            LegoColours.__overwriteColour(17,  (194/255, 218/255, 184/255))
            LegoColours.__overwriteColour(18,  (249/255, 233/255, 153/255))
            LegoColours.__overwriteColour(19,  (215/255, 197/255, 153/255))
            LegoColours.__overwriteColour(20,  (193/255, 202/255, 222/255))
            LegoColours.__overwriteColour(21,  (224/255, 255/255, 176/255))
            LegoColours.__overwriteColour(22,  (107/255,  50/255, 123/255))
            LegoColours.__overwriteColour(23,  ( 35/255,  71/255, 139/255))
            LegoColours.__overwriteColour(25,  (218/255, 133/255,  64/255))
            LegoColours.__overwriteColour(26,  (146/255, 57/255,  120/255))
            LegoColours.__overwriteColour(27,  (164/255, 189/255,  70/255))
            LegoColours.__overwriteColour(28,  (149/255, 138/255, 115/255))
            LegoColours.__overwriteColour(29,  (228/255, 173/255, 200/255))
            LegoColours.__overwriteColour(30,  (172/255, 120/255, 186/255))
            LegoColours.__overwriteColour(31,  (225/255, 213/255, 237/255))
            LegoColours.__overwriteColour(32,  (  0/255,  20/255,  20/255))
            LegoColours.__overwriteColour(33,  (123/255, 182/255, 232/255))
            LegoColours.__overwriteColour(34,  (132/255, 182/255, 141/255))
            LegoColours.__overwriteColour(35,  (217/255, 228/255, 167/255))
            LegoColours.__overwriteColour(36,  (205/255,  84/255,  75/255))
            LegoColours.__overwriteColour(37,  (228/255, 173/255, 200/255))
            LegoColours.__overwriteColour(38,  (255/255,  43/255,   0/225))
            LegoColours.__overwriteColour(40,  (166/255, 145/255, 130/255))
            LegoColours.__overwriteColour(41,  (170/255, 229/255, 255/255))
            LegoColours.__overwriteColour(42,  (198/255, 255/255,   0/255))
            LegoColours.__overwriteColour(43,  (193/255, 223/255, 240/255))
            LegoColours.__overwriteColour(44,  (150/255, 112/255, 159/255))
            LegoColours.__overwriteColour(46,  (247/255, 241/255, 141/255))
            LegoColours.__overwriteColour(47,  (252/255, 252/255, 252/255))
            LegoColours.__overwriteColour(52,  (156/255, 149/255, 199/255))
            LegoColours.__overwriteColour(54,  (255/255, 246/255, 123/255))
            LegoColours.__overwriteColour(57,  (226/255, 176/255,  96/255))
            LegoColours.__overwriteColour(65,  (236/255, 201/255,  53/255))
            LegoColours.__overwriteColour(66,  (202/255, 176/255,   0/255))
            LegoColours.__overwriteColour(67,  (255/255, 255/255, 255/255))
            LegoColours.__overwriteColour(68,  (243/255, 207/255, 155/255))
            LegoColours.__overwriteColour(69,  (142/255,  66/255, 133/255))
            LegoColours.__overwriteColour(70,  (105/255,  64/255,  39/255))
            LegoColours.__overwriteColour(71,  (163/255, 162/255, 164/255))
            LegoColours.__overwriteColour(72,  ( 99/255,  95/255,  97/255))
            LegoColours.__overwriteColour(73,  (110/255, 153/255, 201/255))
            LegoColours.__overwriteColour(74,  (161/255, 196/255, 139/255))
            LegoColours.__overwriteColour(77,  (220/255, 144/255, 149/255))
            LegoColours.__overwriteColour(78,  (246/255, 215/255, 179/255))
            LegoColours.__overwriteColour(79,  (255/255, 255/255, 255/255))
            LegoColours.__overwriteColour(80,  (140/255, 140/255, 140/255))
            LegoColours.__overwriteColour(82,  (219/255, 172/255,  52/255))
            LegoColours.__overwriteColour(84,  (170/255, 125/255,  85/255))
            LegoColours.__overwriteColour(85,  ( 52/255,  43/255, 117/255))
            LegoColours.__overwriteColour(86,  (124/255,  92/255,  69/255))
            LegoColours.__overwriteColour(89,  (155/255, 178/255, 239/255))
            LegoColours.__overwriteColour(92,  (204/255, 142/255, 104/255))
            LegoColours.__overwriteColour(100, (238/255, 196/255, 182/255))
            LegoColours.__overwriteColour(115, (199/255, 210/255,  60/255))
            LegoColours.__overwriteColour(134, (174/255, 122/255,  89/255))
            LegoColours.__overwriteColour(135, (171/255, 173/255, 172/255))
            LegoColours.__overwriteColour(137, (106/255, 122/255, 150/255))
            LegoColours.__overwriteColour(142, (220/255, 188/255, 129/255))
            LegoColours.__overwriteColour(148, ( 62/255,  60/255,  57/255))
            LegoColours.__overwriteColour(151, ( 14/255,  94/255,  77/255))
            LegoColours.__overwriteColour(179, (160/255, 160/255, 160/255))
            LegoColours.__overwriteColour(183, (242/255, 243/255, 242/255))
            LegoColours.__overwriteColour(191, (248/255, 187/255,  61/255))
            LegoColours.__overwriteColour(212, (159/255, 195/255, 233/255))
            LegoColours.__overwriteColour(216, (143/255,  76/255,  42/255))
            LegoColours.__overwriteColour(226, (253/255, 234/255, 140/255))
            LegoColours.__overwriteColour(232, (125/255, 187/255, 221/255))
            LegoColours.__overwriteColour(256, ( 33/255,  33/255,  33/255))
            LegoColours.__overwriteColour(272, ( 32/255,  58/255,  86/255))
            LegoColours.__overwriteColour(273, ( 13/255, 105/255, 171/255))
            LegoColours.__overwriteColour(288, ( 39/255,  70/255,  44/255))
            LegoColours.__overwriteColour(294, (189/255, 198/255, 173/255))
            LegoColours.__overwriteColour(297, (170/255, 127/255,  46/255))
            LegoColours.__overwriteColour(308, ( 53/255,  33/255,   0/255))
            LegoColours.__overwriteColour(313, (171/255, 217/255, 255/255))
            LegoColours.__overwriteColour(320, (123/255,  46/255,  47/255))
            LegoColours.__overwriteColour(321, ( 70/255, 155/255, 195/255))
            LegoColours.__overwriteColour(322, (104/255, 195/255, 226/255))
            LegoColours.__overwriteColour(323, (211/255, 242/255, 234/255))
            LegoColours.__overwriteColour(324, (196/255,   0/255,  38/255))
            LegoColours.__overwriteColour(326, (226/255, 249/255, 154/255))
            LegoColours.__overwriteColour(330, (119/255, 119/255,  78/255))
            LegoColours.__overwriteColour(334, (187/255, 165/255,  61/255))
            LegoColours.__overwriteColour(335, (149/255, 121/255, 118/255))
            LegoColours.__overwriteColour(366, (209/255, 131/255,   4/255))
            LegoColours.__overwriteColour(373, (135/255, 124/255, 144/255))
            LegoColours.__overwriteColour(375, (193/255, 194/255, 193/255))
            LegoColours.__overwriteColour(378, (120/255, 144/255, 129/255))
            LegoColours.__overwriteColour(379, ( 94/255, 116/255, 140/255))
            LegoColours.__overwriteColour(383, (224/255, 224/255, 224/255))
            LegoColours.__overwriteColour(406, (  0/255,  29/255, 104/255))
            LegoColours.__overwriteColour(449, (129/255,   0/255, 123/255))
            LegoColours.__overwriteColour(450, (203/255, 132/255,  66/255))
            LegoColours.__overwriteColour(462, (226/255, 155/255,  63/255))
            LegoColours.__overwriteColour(484, (160/255,  95/255,  52/255))
            LegoColours.__overwriteColour(490, (215/255, 240/255,   0/255))
            LegoColours.__overwriteColour(493, (101/255, 103/255,  97/255))
            LegoColours.__overwriteColour(494, (208/255, 208/255, 208/255))
            LegoColours.__overwriteColour(496, (163/255, 162/255, 164/255))
            LegoColours.__overwriteColour(503, (199/255, 193/255, 183/255))
            LegoColours.__overwriteColour(504, (137/255, 135/255, 136/255))
            LegoColours.__overwriteColour(511, (250/255, 250/255, 250/255))

        # Colour Space Management: Convert these sRGB colour values to Blender's linear RGB colour space
        for key in LegoColours.colours:
            LegoColours.colours[key]["colour"] = LegoColours.sRGBtoLinearRGB(LegoColours.colours[key]["colour"])

    def lightenRGBA(colour, scale):
        # Moves the linear RGB values closer to white
        # scale = 0 means full white
        # scale = 1 means color stays same
        colour = ((1.0 - colour[0]) * scale, 
                  (1.0 - colour[1]) * scale, 
                  (1.0 - colour[2]) * scale, 
                  colour[3])
        return (Math.clamp01(1.0 - colour[0]), 
                Math.clamp01(1.0 - colour[1]), 
                Math.clamp01(1.0 - colour[2]), 
                colour[3])

    def __init__(self):
        LegoColours.__readColourTable()


# **************************************************************************************
# **************************************************************************************
class FileSystem:
    """
    Reads text files in different encodings. Locates full filepath for a part.
    """

    def __checkEncoding(filepath):
        """Check the encoding of a file for Endian encoding."""

        # Open it, read just the area containing a possible byte mark
        with open(filepath, "rb") as encode_check:
            encoding = encode_check.readline(3)

        # The file uses UCS-2 (UTF-16) Big Endian encoding
        if encoding == b"\xfe\xff\x00":
            return "utf_16_be"

        # The file uses UCS-2 (UTF-16) Little Endian
        elif encoding == b"\xff\xfe0":
            return "utf_16_le"

        # Use LDraw model standard UTF-8
        else:
            return "utf_8"

    def readTextFile(filepath):
        """Read a text file, with various checks for type of encoding"""

        lines = None
        if os.path.exists(filepath):
            # Try to read using the suspected encoding
            file_encoding = FileSystem.__checkEncoding(filepath)
            try:
                with open(filepath, "rt", encoding=file_encoding) as f_in:
                    lines = f_in.readlines()
            except:
                # If all else fails, read using Latin 1 encoding
                with open(filepath, "rt", encoding="latin_1") as f_in:
                    lines = f_in.readlines()

        return lines

    def locate(filename):
        """Given a file name of an ldraw file, find the full path"""

        partName = filename.replace("\\", os.path.sep)
        partName = os.path.expanduser(partName)

        for path in Configure.searchPaths:
            # Perform a direct check
            fullPathName = os.path.join(path, partName)
            if os.path.exists(fullPathName):
                return fullPathName
            else:
                # Perform a normalized check
                fullPathName = os.path.join(path, partName.lower())
                print(fullPathName)
                if os.path.exists(fullPathName):
                    return fullPathName

        return None


# **************************************************************************************
# **************************************************************************************
class CachedFiles:
    """Cached dictionary of LDrawFile objects keyed by filename"""

    __cache = {}        # Dictionary

    def getCached(key):
        # get the file from the cache associated with the exact key, and if none is
		# found, try it with case insensitive keys
        similarKey = None
        for cacheKey in CachedFiles.__cache:
            if cacheKey == key:
                return CachedFiles.__cache[key]
            elif cacheKey.lower() == key.lower():
                similarKey = cacheKey
        if similarKey is not None:
            return CachedFiles.__cache[similarKey]
        else:
            return None		

    def addToCache(key, value):
        CachedFiles.__cache[key] = value

    def clearCache():
        CachedFiles.__cache = {}


# **************************************************************************************
# **************************************************************************************
class CachedGeometry:
    """Cached dictionary of LDrawGeometry objects"""

    __cache = {}        # Dictionary

    def getCached(key):
        if key in CachedFiles.__cache:
            return CachedFiles.__cache[key]
        return None

    def addToCache(key, value):
        CachedFiles.__cache[key] = value

    def clearCache():
        CachedFiles.__cache = {}


# **************************************************************************************
# **************************************************************************************
class LDrawGeometry:
    """Stores the geometry for an LDrawFile"""

    def __init__(self):
        self.points = []
        self.faces = []
        self.faceColours = []
        self.culling = []
        self.windingCCW = []
        self.edges = []
        self.edgeIndices = []

    def parseFace(self, parameters, cull, ccw):
        """Parse a face from parameters"""

        num_points = int(parameters[0])
        colourName = parameters[1]

        newPoints = []
        for i in range(num_points):
            blenderPos = Math.scaleMatrix * mathutils.Vector( (float(parameters[i * 3 + 2]),
                                                               float(parameters[i * 3 + 3]), 
                                                               float(parameters[i * 3 + 4])) )
            newPoints.append(blenderPos)

        # Fix "bowtie" quadrilaterals (see http://wiki.ldraw.org/index.php?title=LDraw_technical_restrictions#Complex_quadrilaterals)
        if num_points == 4:
            nA = (newPoints[1] - newPoints[0]).cross(newPoints[2] - newPoints[0])
            nB = (newPoints[2] - newPoints[1]).cross(newPoints[3] - newPoints[1])
            if (nA.dot(nB) < 0):
                newPoints[2], newPoints[3] = newPoints[3], newPoints[2]

        pointCount = len(self.points)
        newFace = list(range(pointCount, pointCount + num_points))
        self.points.extend(newPoints)
        self.faces.append(newFace)
        self.faceColours.append(colourName)
        self.culling.append(cull)
        self.windingCCW.append(ccw)

    def parseEdge(self, parameters):
        """Parse an edge from parameters"""

        colourName = parameters[1]
        if colourName == "24":
            blenderPos1 = Math.scaleMatrix * mathutils.Vector( (float(parameters[2]),
                                                                float(parameters[3]), 
                                                                float(parameters[4])) )
            blenderPos2 = Math.scaleMatrix * mathutils.Vector( (float(parameters[5]),
                                                                float(parameters[6]), 
                                                                float(parameters[7])) )
            self.edges.append((blenderPos1, blenderPos2))

    def verify(self, face, numPoints):
        for i in face:
            assert i < numPoints
            assert i >= 0

    def appendGeometry(self, geometry, matrix, isStudLogo, parentMatrix, cull, invert):
        combinedMatrix = parentMatrix * matrix
        isReflected = combinedMatrix.determinant() < 0.0
        reflectStudLogo = isStudLogo and isReflected

        fixedMatrix = matrix.copy()
        if reflectStudLogo:
            fixedMatrix = matrix * Math.reflectionMatrix
            invert = not invert

        # Append face information
        pointCount = len(self.points)
        newIndices = []
        for index, face in enumerate(geometry.faces):
            # Gather points for this face (and transform points)
            newPoints = []
            for i in face:
                newPoints.append(fixedMatrix * geometry.points[i])

            # Add clockwise and/or anticlockwise sets of points as appropriate
            newFace = face.copy()
            for i in range(len(newFace)):
                newFace[i] += pointCount
            
            faceCCW = geometry.windingCCW[index] != invert
            faceCull = geometry.culling[index] and cull
            
            # If we are going to resolve ambiguous normals by "best guess" we will let 
            # Blender calculate that for us later. Just cull with arbitrary winding for now.
            if not faceCull:
                if Options.resolveAmbiguousNormals == "guess":
                    faceCull = True

            if faceCCW or not faceCull:
                self.points.extend(newPoints)
                self.faces.append(newFace)
                self.windingCCW.append(True)
                self.culling.append(True)
                newIndices.append(geometry.faceColours[index])
                self.verify(newFace, len(self.points))

            if not faceCull:
                newFace = newFace.copy()
                pointCount += len(newPoints)
                for i in range(len(newFace)):
                    newFace[i] += len(newPoints)

            if not faceCCW or not faceCull:
                self.points.extend(newPoints[::-1])
                self.faces.append(newFace)
                self.windingCCW.append(True)
                self.culling.append(True)
                newIndices.append(geometry.faceColours[index])
                self.verify(newFace, len(self.points))

        self.faceColours.extend(newIndices)
        assert len(self.faces) == len(self.faceColours)

        # Append edge information
        newEdges = []
        for edge in geometry.edges:
            newEdges.append( (fixedMatrix * edge[0], fixedMatrix * edge[1]) )
        self.edges.extend(newEdges)


# **************************************************************************************
# **************************************************************************************
class LDrawNode:
    """A node in the hierarchy. References one LDrawFile"""

    def __init__(self, filename, isFullFilepath, colourName=Options.defaultColour, matrix=Math.identityMatrix, bfcCull=True, bfcInverted=False, isLSynthPart=False, isSubPart=False, isRootNode=True, groupNames=[]):
        self.filename       = filename
        self.isFullFilepath = isFullFilepath
        self.matrix         = matrix
        self.colourName     = colourName
        self.bfcInverted    = bfcInverted
        self.bfcCull        = bfcCull
        self.file           = None
        self.isLSynthPart   = isLSynthPart
        self.isSubPart      = isSubPart
        self.isRootNode     = isRootNode
        self.groupNames     = groupNames.copy()

    def isBlenderObjectNode(self):
        """
        Calculates if this node should become a Blender object.
        Some nodes will become objects in Blender, some will not.
        Typically nodes that reference a model or a part become Blender Objects, but not nodes that reference subparts.
        """

        # The root node is always a Blender node
        if self.isRootNode:
            return True

        # General rule: We are a Blender object if we are a part or higher (ie. if we are not a subPart)
        isBON = not self.isSubPart

        # Exception #1 - If flattening the hierarchy, we only want parts (not models)
        if Options.flattenHierarchy:
            isBON = self.file.isPart and not self.isSubPart

        # Exception #2 - We are not a Blender Object if we are an LSynth part (so that all LSynth parts become a single mesh)
        if self.isLSynthPart:
            isBON = False

        # Exception #3 - We are a Blender Object if we are a stud to be instanced
        if Options.instanceStuds and self.file.isStud:
            isBON = True

        return isBON

    def load(self):
        # Is this file in the cache?
        self.file = CachedFiles.getCached(self.filename)
        if self.file is None:
            # Not in cache, so load file
            self.file = LDrawFile(self.filename, self.isFullFilepath, None, self.isSubPart)
            assert self.file is not None

            # Add the new file to the cache
            CachedFiles.addToCache(self.filename, self.file)

        # Load any children
        for child in self.file.childNodes:
            child.load()

    def __bakeColours(self, faceColours, realColourName):
        # Replaces the default colour 16 in our faceColours list with a specific colour
        return list(map((lambda c: LDrawNode.resolveColour(c, realColourName)), faceColours))

    def resolveColour(colourName, realColourName):
        if colourName == "16":
            return realColourName
        return colourName

    def printBFC(self, depth=0):
        # For debugging, displays BFC information

        debugPrint("{0}Node {1} has cull={2} and invert={3} det={4}".format(" "*(depth*4), self.filename, self.bfcCull, self.bfcInverted, self.matrix.determinant()))
        for child in self.file.childNodes:
            child.printBFC(depth + 1)

    def getBFCCode(accumCull, accumInvert, bfcCull, bfcInverted):
        index = (8 if accumCull else 0) +  (4 if accumInvert else 0) + (2 if bfcCull else 0) + (1 if bfcInverted else 0)
        # Normally meshes are culled and not inverted, so don't bother with a code in this case
        if index == 10:
            return ""
        # If this is out of the ordinary, add a code that makes it a unique name to cache the mesh properly
        return "_{0}".format(index)

    def getBlenderGeometry(self, realColourName, basename, parentMatrix=Math.identityMatrix, accumCull=True, accumInvert=False):
        """
        Returns the geometry for the Blender Object at this node.

        It accumulates the geometry of itself with all the geometry of it's children 
        recursively (specifically - those children that are not Blender Object nodes).

        The result will become a single mesh in Blender.
        """

        assert self.file is not None

        accumCull = accumCull and self.bfcCull
        accumInvert = accumInvert != self.bfcInverted

        ourColourName = LDrawNode.resolveColour(self.colourName, realColourName)
        code = LDrawNode.getBFCCode(accumCull, accumInvert, self.bfcCull, self.bfcInverted)
        meshName = "Mesh_{0}_{1}{2}".format(basename, ourColourName, code)
        key = (self.filename, ourColourName, accumCull, accumInvert, self.bfcCull, self.bfcInverted)
        bakedGeometry = CachedGeometry.getCached(key)
        if bakedGeometry is None:
            combinedMatrix = parentMatrix * self.matrix

            # Start with a copy of our file's geometry
            assert len(self.file.geometry.faces) == len(self.file.geometry.faceColours)
            bakedGeometry = LDrawGeometry()
            bakedGeometry.appendGeometry(self.file.geometry, Math.identityMatrix, False, combinedMatrix, self.bfcCull, self.bfcInverted)

            # Replace the default colour
            bakedGeometry.faceColours = self.__bakeColours(bakedGeometry.faceColours, ourColourName)

            # Append each child's geometry
            for child in self.file.childNodes:
                assert child.file is not None
                if not child.isBlenderObjectNode():
                    childColourName = LDrawNode.resolveColour(child.colourName, ourColourName)
                    childMeshName, bg = child.getBlenderGeometry(childColourName, basename, combinedMatrix, accumCull, accumInvert)

                    isStudLogo = child.file.isStudLogo
                    bakedGeometry.appendGeometry(bg, child.matrix, isStudLogo, combinedMatrix, self.bfcCull, self.bfcInverted)

            CachedGeometry.addToCache(key, bakedGeometry)
        assert len(bakedGeometry.faces) == len(bakedGeometry.faceColours)
        return (meshName, bakedGeometry)


# **************************************************************************************
# **************************************************************************************
class LDrawFile:
    """Stores the contents of a single LDraw file.
    Specifically this represents an LDR, L3B, DAT or one '0 FILE' section of an MPD.
    Splits up an MPD file into '0 FILE' sections and caches them."""

    def __loadLegoFile(self, filepath, isFullFilepath):
        # Resolve full filepath if necessary
        if isFullFilepath is False:
            result = FileSystem.locate(filepath)
            if result is None:
                printWarningOnce("Missing file {0}".format(filepath))
                return False
            filepath = result

        # Load text into local lines variable
        lines = FileSystem.readTextFile(filepath)
        if lines is None:
            printWarningOnce("Could not read file {0}".format(filepath))
            lines = []

        # MPD files have separate sections between '0 FILE' and '0 NOFILE' lines.
        # Split into sections between "0 FILE" and "0 NOFILE" lines
        sections = []

        startLine = 0
        endLine = 0
        lineCount = 0
        sectionFilename = filepath
        foundEnd = False

        for line in lines:
            parameters = line.strip().split()
            if len(parameters) > 2:
                if parameters[0] == "0" and parameters[1] == "FILE":
                    if foundEnd == False:
                        endLine = lineCount
                        if endLine > startLine:
                            sections.append((sectionFilename, lines[startLine:endLine]))

                    startLine = lineCount
                    foundEnd = False
                    sectionFilename = " ".join(parameters[2:])

                if parameters[0] == "0" and parameters[1] == "NOFILE":
                    endLine = lineCount
                    foundEnd = True
                    sections.append((sectionFilename, lines[startLine:endLine]))
            lineCount += 1

        if foundEnd == False:
            endLine = lineCount
            if endLine > startLine:
                sections.append((sectionFilename, lines[startLine:endLine]))

        if len(sections) == 0:
            return False

        # First section is the main one
        self.filename = sections[0][0]
        self.lines = sections[0][1]

        # Remaining sections are loaded into the cached files
        for (sectionFilename, lines) in sections[1:]:
            # Load section
            file = LDrawFile(sectionFilename, False, lines, False)
            assert file is not None

            # Cache section
            CachedFiles.addToCache(sectionFilename, file)

        return True

    def __isStud(filename):
        """Is this file a stud?"""

        if LDrawFile.__isStudLogo(filename):
            return True

        # Extract just the filename, in lower case
        filename = filename.replace("\\", os.path.sep)
        name = os.path.basename(filename).lower()

        return name in (
            "stud2.dat", 
            "stud6.dat", 
            "stud6a.dat",
            "stud7.dat", 
            "stud10.dat",
            "stud13.dat",
            "stud15.dat",
            "stud20.dat",
            "studa.dat",
            "stud-logo3.dat",   "stud-logo4.dat",   "stud-logo5.dat", 
            "stud2-logo3.dat",  "stud2-logo4.dat",  "stud2-logo5.dat",
            "stud6-logo3.dat",  "stud6-logo4.dat",  "stud6-logo5.dat", 
            "stud6a-logo3.dat", "stud6a-logo4.dat", "stud6a-logo5.dat", 
            "stud7-logo3.dat",  "stud7-logo4.dat",  "stud7-logo5.dat", 
            "stud10-logo3.dat", "stud10-logo4.dat", "stud10-logo5.dat", 
            "stud13-logo3.dat", "stud13-logo4.dat", "stud13-logo5.dat", 
            "stud15-logo3.dat", "stud15-logo4.dat", "stud15-logo5.dat", 
            "stud20-logo3.dat", "stud20-logo4.dat", "stud20-logo5.dat", 
            "studa-logo3.dat",  "studa-logo4.dat",  "studa-logo5.dat", 
             )

    def __isStudLogo(filename):
        """Is this file a stud logo?"""

        # Extract just the filename, in lower case
        filename = filename.replace("\\", os.path.sep)
        name = os.path.basename(filename).lower()

        return name in ("logo3.dat", "logo4.dat", "logo5.dat")

    def __init__(self, filename, isFullFilepath, lines = None, isSubPart=False):
        """Loads an LDraw file (LDR, L3B, DAT or MPD)"""

        self.filename         = filename
        self.lines            = lines
        self.isPart           = False
        self.isSubPart        = isSubPart
        self.isStud           = LDrawFile.__isStud(filename)
        self.isStudLogo       = LDrawFile.__isStudLogo(filename)
        self.isLSynthPart     = False
        self.isDoubleSided    = False
        self.geometry         = LDrawGeometry()
        self.childNodes       = []
        self.bfcCertified     = None

        if self.lines is None:
            # Load the file into self.lines
            if not self.__loadLegoFile(self.filename, isFullFilepath):
                return

        # BFC = Back face culling. The rules are arcane and complex, but at least
        #       it's kind of documented: http://www.ldraw.org/article/415.html
        bfcLocalCull          = True
        bfcWindingCCW         = True
        bfcInvertNext         = False
        processingLSynthParts = False
        
        currentGroupNames = []

        #debugPrint("Processing file {0}, isSubPart = {1}, found {2} lines".format(self.filename, self.isSubPart, len(self.lines)))

        for line in self.lines:
            parameters = line.strip().split()

            # Skip empty lines
            if len(parameters) == 0:
                continue
                
            # Pad with empty values to ease parsing
            while len(parameters) < 5:
                parameters.append(None)

            # Parse LDraw comments (some of which have special significance)
            if parameters[0] == "0":
                if parameters[1] == "!LDRAW_ORG":
                    partType = parameters[2].lower()
                    if 'part' in partType:
                        self.isPart = True
                    if 'subpart' in partType:
                        self.isSubPart = True
                    if 'primitive' in partType:
                        self.isSubPart = True
                    #if 'shortcut' in partType:
                    #    self.isPart = True

                if parameters[1] == "BFC":
                    # If unsure about being certified yet...
                    if self.bfcCertified is None:
                        if parameters[2] == "NOCERTIFY":
                            self.bfcCertified = False
                        else:
                            self.bfcCertified = True
                    if "CW" in parameters:
                        bfcWindingCCW = False
                    if "CCW" in parameters:
                        bfcWindingCCW = True
                    if "CLIP" in parameters:
                        bfcLocalCull = True
                    if "NOCLIP" in parameters:
                        bfcLocalCull = False
                    if "INVERTNEXT" in parameters:
                        bfcInvertNext = True
                if parameters[1] == "SYNTH":
                    if parameters[2] == "SYNTHESIZED":
                        if parameters[3] == "BEGIN":
                            processingLSynthParts = True
                        if parameters[3] == "END":
                            processingLSynthParts = False
                if parameters[1] == "!LDCAD":
                    if parameters[2] == "GENERATED":
                        processingLSynthParts = True
                if parameters[1] == "!LEOCAD":
                    if parameters[2] == "GROUP":
                        if parameters[3] == "BEGIN":
                            currentGroupNames.append(" ".join(parameters[4:]))
                        elif parameters[3] == "END":
                            currentGroupNames.pop(-1)

            else:
                if self.bfcCertified is None:
                    self.bfcCertified = False

                self.isModel = (not self.isPart) and (not self.isSubPart)

                # Parse a File reference
                if parameters[0] == "1":
                    (x, y, z, a, b, c, d, e, f, g, h, i) = map(float, parameters[2:14])
                    (x, y, z) = Math.scaleMatrix * mathutils.Vector((x, y, z))
                    localMatrix = mathutils.Matrix( ((a, b, c, x), (d, e, f, y), (g, h, i, z), (0, 0, 0, 1)) )

                    new_filename = " ".join(parameters[14:])
                    new_colourName = parameters[1]

                    det = localMatrix.determinant()
                    if det < 0:
                        bfcInvertNext = not bfcInvertNext
                    canCullChildNode = (self.bfcCertified or self.isModel) and bfcLocalCull and (det != 0)

                    newNode = LDrawNode(new_filename, False, new_colourName, localMatrix, canCullChildNode, bfcInvertNext, processingLSynthParts, not self.isModel, False, currentGroupNames)
                    self.childNodes.append(newNode)

                # Parse an edge
                elif parameters[0] == "2":
                    self.geometry.parseEdge(parameters)

                # Parse a Face (either a triangle or a quadrilateral)
                elif parameters[0] == "3" or parameters[0] == "4":
                    if self.bfcCertified is None:
                        self.bfcCertified = False
                    if not self.bfcCertified or not bfcLocalCull:
                        printWarningOnce("Found double-sided polygons in file {0}".format(self.filename))
                        self.isDoubleSided = True

                    assert len(self.geometry.faces) == len(self.geometry.faceColours)
                    self.geometry.parseFace(parameters, self.bfcCertified and bfcLocalCull, bfcWindingCCW)
                    assert len(self.geometry.faces) == len(self.geometry.faceColours)

                bfcInvertNext = False

        #debugPrint("File {0} is part = {1}, is subPart = {2}, isModel = {3}".format(filename, self.isPart, isSubPart, self.isModel))


# **************************************************************************************
# **************************************************************************************
class BlenderMaterials:
    """Creates and stores a cache of materials for Blender"""

    __material_list = {}

    def __getGroupName(name):
        if Options.instructionsLook:
            return name + " Instructions"
        return name

    def __setBlenderRenderProperties(material, nodes, links, col):
        """Get Blender Internal Material Values."""
        material.diffuse_color = col["colour"]

        alpha = col["alpha"]
        if alpha < 1.0:
            material.use_transparency = not Options.instructionsLook
            material.alpha = alpha

        material.emit = col["luminance"] / 100

        if col["material"] == "CHROME":
            material.specular_intensity = 1.4
            material.roughness = 0.01
            material.raytrace_mirror.use = True
            material.raytrace_mirror.reflect_factor = 0.3

        elif col["material"] == "PEARLESCENT":
            material.specular_intensity = 0.1
            material.roughness = 0.32
            material.raytrace_mirror.use = True
            material.raytrace_mirror.reflect_factor = 0.07

        elif col["material"] == "RUBBER":
            material.specular_intensity = 0.19

        elif col["material"] == "METAL":
            material.specular_intensity = 1.473
            material.specular_hardness = 292
            material.diffuse_fresnel = 0.93
            material.darkness = 0.771
            material.roughness = 0.01
            material.raytrace_mirror.use = True
            material.raytrace_mirror.reflect_factor = 0.9

        #elif col["material"] == "GLITTER":
        #    slot = material.texture_slots.add()
        #    tex = bpy.data.textures.new("GlitterTex", type = "STUCCI")
        #    tex.use_color_ramp = True
        #
        #    slot.texture = tex

        else:
            material.specular_intensity = 0.2

        # Create input and output nodes, and link them together
        input = nodes.new('ShaderNodeMaterial')
        input.location = 0, -250
        input.material = material
        output = nodes.new('ShaderNodeOutput')
        output.location = 400, -250

        links.new(input.outputs[0], output.inputs[0])

        if Options.instructionsLook and alpha < 1.0:
            mult = nodes.new('ShaderNodeMath')
            mult.operation = 'MULTIPLY'
            mult.location = 200, -410
            links.new(input.outputs[1], mult.inputs[0])
            links.new(mult.outputs[0], output.inputs[1])
        else:
            links.new(input.outputs[1], output.inputs[1])


    def __createNodeBasedMaterial(blenderName, col):
        """Get Cycles Material Values."""

        # Reuse current material if it exists, otherwise create a new material
        if bpy.data.materials.get(blenderName) is None:
            material = bpy.data.materials.new(blenderName)
        else:
            material = bpy.data.materials[blenderName]

        # Use nodes
        material.use_nodes = True

        if Options.instructionsLook:
            material.use_shadeless = True
            material.diffuse_intensity = 1.0
            material.translucency = 0
            if col is not None:
                colour = col["colour"] + (1.0,)
                R = colour[0]
                G = colour[1]
                B = colour[2]
                
                # Measure the perceived brightness of colour
                brightness = math.sqrt( 0.299*R*R + 0.587*G*G + 0.114*B*B )

                # Dark colours have white lines
                if brightness < 0.02:
                    material.line_color = (1.0, 1.0, 1.0, 1.0)

        nodes = material.node_tree.nodes
        links = material.node_tree.links

        # Remove any existing nodes
        for n in nodes:
            nodes.remove(n)

        if col is not None:
            BlenderMaterials.__setBlenderRenderProperties(material, nodes, links, col)

            colour = col["colour"] + (1.0,)
            isTransparent = col["alpha"] < 1.0

            if Options.instructionsLook:
                BlenderMaterials.__createCyclesBasic(nodes, links, colour, col["alpha"])
            elif col["name"] == "Milky_White":
                BlenderMaterials.__createCyclesMilkyWhite(nodes, links, colour)
            elif col["luminance"] > 0:
                BlenderMaterials.__createCyclesEmission(nodes, links, colour, col["alpha"], col["luminance"])
            elif col["material"] == "CHROME":
                BlenderMaterials.__createCyclesChrome(nodes, links, colour)
            elif col["material"] == "PEARLESCENT":
                BlenderMaterials.__createCyclesPearlescent(nodes, links, colour)
            elif col["material"] == "METAL":
                BlenderMaterials.__createCyclesMetal(nodes, links, colour)
            elif col["material"] == "GLITTER":
                BlenderMaterials.__createCyclesGlitter(nodes, links, colour, col["secondary_colour"])
            elif col["material"] == "SPECKLE":
                BlenderMaterials.__createCyclesSpeckle(nodes, links, colour, col["secondary_colour"])
            elif col["material"] == "RUBBER":
                BlenderMaterials.__createCyclesRubber(nodes, links, colour, col["alpha"])
            else:
                BlenderMaterials.__createCyclesBasic(nodes, links, colour, col["alpha"])

            if Options.curvedWalls and not Options.instructionsLook:
                BlenderMaterials.__createCyclesConcaveWalls(nodes, links, 0.2)

            material["Lego.isTransparent"] = isTransparent
            return material

        BlenderMaterials.__createCyclesBasic(nodes, links, (1.0, 1.0, 0.0, 1.0), 1.0)
        material["Lego.isTransparent"] = False
        return material

    def __nodeConcaveWalls(nodes, strength, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Concave Walls')]
        node.location = x, y
        node.inputs['Strength'].default_value = strength
        return node

    def __nodeLegoStandard(nodes, colour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Standard')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        return node

    def __nodeLegoTransparent(nodes, colour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Transparent')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        return node

    def __nodeLegoRubberSolid(nodes, colour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Rubber Solid')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        return node

    def __nodeLegoRubberTranslucent(nodes, colour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Rubber Translucent')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        return node

    def __nodeLegoEmission(nodes, colour, luminance, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Emission')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        node.inputs['Luminance'].default_value = luminance
        return node

    def __nodeLegoChrome(nodes, colour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Chrome')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        return node

    def __nodeLegoPearlescent(nodes, colour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Pearlescent')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        return node

    def __nodeLegoMetal(nodes, colour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Metal')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        return node

    def __nodeLegoGlitter(nodes, colour, glitterColour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Glitter')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        node.inputs['Glitter Color'].default_value = glitterColour
        return node

    def __nodeLegoSpeckle(nodes, colour, speckleColour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Speckle')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        node.inputs['Speckle Color'].default_value = speckleColour
        return node

    def __nodeLegoMilkyWhite(nodes, colour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Milky White')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        return node

    def __nodeMix(nodes, factor, x, y):
        node = nodes.new('ShaderNodeMixShader')
        node.location = x, y
        node.inputs['Fac'].default_value = factor
        return node

    def __nodeOutput(nodes, x, y):
        node = nodes.new('ShaderNodeOutputMaterial')
        node.location = x, y
        return node

    def nodeDielectric(nodes, roughness, reflection, transparency, ior, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups['PBR-Dielectric']
        node.location = x, y
        node.inputs['Roughness'].default_value = roughness
        node.inputs['Reflection'].default_value = reflection
        node.inputs['Transparency'].default_value = transparency
        node.inputs['IOR'].default_value = ior
        return node

    def __nodeDiffuse(nodes, roughness, x, y):
        node = nodes.new('ShaderNodeBsdfDiffuse')
        node.location = x, y
        node.inputs['Color'].default_value = (1,1,1,1)
        node.inputs['Roughness'].default_value = roughness
        return node

    def __nodeGlass(nodes, roughness, ior, distribution, x, y):
        node = nodes.new('ShaderNodeBsdfGlass')
        node.location = x, y
        node.distribution = distribution
        node.inputs['Color'].default_value = (1,1,1,1)
        node.inputs['Roughness'].default_value = roughness
        node.inputs['IOR'].default_value = ior
        return node

    def __nodeFresnel(nodes, ior, x, y):
        node = nodes.new('ShaderNodeFresnel')
        node.location = x, y
        node.inputs['IOR'].default_value = ior
        return node

    def __nodeGlossy(nodes, colour, roughness, distribution, x, y):
        node = nodes.new('ShaderNodeBsdfGlossy')
        node.location = x, y
        node.distribution = distribution
        node.inputs['Color'].default_value = colour
        node.inputs['Roughness'].default_value = roughness
        return node

    def __nodeTranslucent(nodes, x, y):
        node = nodes.new('ShaderNodeBsdfTranslucent')
        node.location = x, y
        return node

    def __nodeTransparent(nodes, x, y):
        node = nodes.new('ShaderNodeBsdfTransparent')
        node.location = x, y
        return node

    def __nodeLightPath(nodes, x, y):
        node = nodes.new('ShaderNodeLightPath')
        node.location = x, y
        return node

    def __nodeMath(nodes, operation, x, y):
        node = nodes.new('ShaderNodeMath')
        node.operation = operation
        node.location = x, y
        return node

    def __nodeEmission(nodes, x, y):
        node = nodes.new('ShaderNodeEmission')
        node.location = x, y
        return node

    def __nodeVoronoi(nodes, scale, x, y):
        node = nodes.new('ShaderNodeTexVoronoi')
        node.location = x, y
        node.coloring = 'CELLS'
        node.inputs['Scale'].default_value = scale
        return node

    def __nodeGamma(nodes, gamma, x, y):
        node = nodes.new('ShaderNodeGamma')
        node.location = x, y
        node.inputs['Gamma'].default_value = gamma
        return node

    def __nodeColorRamp(nodes, pos1, colour1, pos2, colour2, x, y):
        node = nodes.new('ShaderNodeValToRGB')
        node.location = x, y
        node.color_ramp.elements[0].position = pos1
        node.color_ramp.elements[0].color = colour1
        node.color_ramp.elements[1].position = pos2
        node.color_ramp.elements[1].color = colour2
        return node

    def __createCyclesConcaveWalls(nodes, links, strength):
        """Concave wall normals for Cycles render engine"""
        node = BlenderMaterials.__nodeConcaveWalls(nodes, strength, -200, 5)
        out = nodes['Group']
        links.new(node.outputs['Normal'], out.inputs['Normal'])

    def __createCyclesBasic(nodes, links, diffColour, alpha):
        """Basic Material for Cycles render engine."""

        if alpha < 1:
            node = BlenderMaterials.__nodeLegoTransparent(nodes, diffColour, 0, 5)
        else:
            node = BlenderMaterials.__nodeLegoStandard(nodes, diffColour, 0, 5)

        out = BlenderMaterials.__nodeOutput(nodes, 200, 0)
        links.new(node.outputs['Shader'], out.inputs[0])

    def __createCyclesEmission(nodes, links, diffColour, alpha, luminance):
        """Emission material for Cycles render engine."""

        node = BlenderMaterials.__nodeLegoEmission(nodes, diffColour, luminance/100.0, 0, 5)
        out = BlenderMaterials.__nodeOutput(nodes, 200, 0)
        links.new(node.outputs['Shader'], out.inputs[0])

    def __createCyclesChrome(nodes, links, diffColour):
        """Chrome material for Cycles render engine."""

        node = BlenderMaterials.__nodeLegoChrome(nodes, diffColour, 0, 5)
        out = BlenderMaterials.__nodeOutput(nodes, 200, 0)
        links.new(node.outputs['Shader'], out.inputs[0])

    def __createCyclesPearlescent(nodes, links, diffColour):
        """Pearlescent material for Cycles render engine."""

        node = BlenderMaterials.__nodeLegoPearlescent(nodes, diffColour, 0, 5)
        out = BlenderMaterials.__nodeOutput(nodes, 200, 0)
        links.new(node.outputs['Shader'], out.inputs[0])

    def __createCyclesMetal(nodes, links, diffColour):
        """Metal material for Cycles render engine."""

        node = BlenderMaterials.__nodeLegoMetal(nodes, diffColour, 0, 5)
        out = BlenderMaterials.__nodeOutput(nodes, 200, 0)
        links.new(node.outputs['Shader'], out.inputs[0])

    def __createCyclesGlitter(nodes, links, diffColour, glitterColour):
        """Glitter material for Cycles render engine."""

        glitterColour = LegoColours.lightenRGBA(glitterColour, 0.5)
        node = BlenderMaterials.__nodeLegoGlitter(nodes, diffColour, glitterColour, 0, 5)
        out = BlenderMaterials.__nodeOutput(nodes, 200, 0)
        links.new(node.outputs['Shader'], out.inputs[0])

    def __createCyclesSpeckle(nodes, links, diffColour, speckleColour):
        """Speckle material for Cycles render engine."""

        speckleColour = LegoColours.lightenRGBA(speckleColour, 0.5)
        node = BlenderMaterials.__nodeLegoSpeckle(nodes, diffColour, speckleColour, 0, 5)
        out = BlenderMaterials.__nodeOutput(nodes, 200, 0)
        links.new(node.outputs['Shader'], out.inputs[0])

    def __createCyclesRubber(nodes, links, diffColour, alpha):
        """Rubber material colours for Cycles render engine."""

        out    = BlenderMaterials.__nodeOutput(nodes, 200, 0)

        if alpha < 1.0:
            rubber = BlenderMaterials.__nodeLegoRubberTranslucent(nodes, diffColour, 0, 5)
        else:
            rubber = BlenderMaterials.__nodeLegoRubberSolid(nodes, diffColour, 0, 5)

        links.new(rubber.outputs[0], out.inputs[0])

    def __createCyclesMilkyWhite(nodes, links, diffColour):
        """Milky White material for Cycles render engine."""

        node = BlenderMaterials.__nodeLegoMilkyWhite(nodes, diffColour, 0, 5)
        out = BlenderMaterials.__nodeOutput(nodes, 200, 0)
        links.new(node.outputs['Shader'], out.inputs[0])

    def __is_int(s):
        try:
            int(s)
            return True
        except ValueError:
            return False

    def __getColourData(colourName):
        """Get the colour data associated with the colour name"""

        # Try the LDraw defined colours
        if BlenderMaterials.__is_int(colourName):
            colourInt = int(colourName)
            if colourInt in LegoColours.colours:
                return LegoColours.colours[colourInt]

        # Handle direct colours
        # Direct colours are documented here: http://www.hassings.dk/l3/l3p.html
        linearRGBA = LegoColours.hexStringToLinearRGBA(colourName)
        if linearRGBA is None:
            printWarningOnce("WARNING: Could not decode {0} to a colour".format(colourName))
            return None
        return {
            "name":         colourName,
            "colour":       linearRGBA[0:3],
            "alpha":        linearRGBA[3],
            "luminance":    0.0,
            "material":     "BASIC"
        }

    def getMaterial(colourName):
        # If it's already in the cache, use that
        if (colourName in BlenderMaterials.__material_list):
            result = BlenderMaterials.__material_list[colourName]
            return result

        # Create a name for the material based on the colour
        if Options.instructionsLook:
            blenderName = "MatInst_{0}".format(colourName)
        elif Options.curvedWalls:
            blenderName = "Material_{0}_c".format(colourName)
        else:
            blenderName = "Material_{0}".format(colourName)    

        # If the name already exists in Blender, use that
        if Options.overwriteExistingMaterials is False:
            if blenderName in bpy.data.materials:
                return bpy.data.materials[blenderName]

        # Create new material
        col = BlenderMaterials.__getColourData(colourName)
        material = BlenderMaterials.__createNodeBasedMaterial(blenderName, col)

        if material is None:
            printWarningOnce("Could not create material for blenderName {0}".format(blenderName))

        # Add material to cache
        BlenderMaterials.__material_list[colourName] = material
        return material

    def clearCache():
        BlenderMaterials.__material_list = {}

    # **************************************************************************************
    def __createGroup(name, x1, y1, x2, y2, createShaderOutput):
        group = bpy.data.node_groups.new(name, 'ShaderNodeTree')

        # create input node
        node_input = group.nodes.new('NodeGroupInput')
        node_input.location = (x1,y1)

        # create output node
        node_output = group.nodes.new('NodeGroupOutput')
        node_output.location = (x2,y2)
        if createShaderOutput:
            group.outputs.new('NodeSocketShader','Shader')
        return (group, node_input, node_output)

    # **************************************************************************************
    def __createBlenderDistanceToCenterNodeGroup():
        if bpy.data.node_groups.get('Distance-To-Center') is None:
            debugPrint("createBlenderDistanceToCenterNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('Distance-To-Center', -930, 0, 240, 0, False)
            group.outputs.new('NodeSocketVectorDirection', 'Vector')

            # create nodes
            node_texture_coordinate = group.nodes.new('ShaderNodeTexCoord')
            node_texture_coordinate.location = -730, 0

            node_vector_subtraction1 = group.nodes.new('ShaderNodeVectorMath')
            node_vector_subtraction1.operation = 'SUBTRACT'
            node_vector_subtraction1.inputs[1].default_value[0] = 0.5
            node_vector_subtraction1.inputs[1].default_value[1] = 0.5
            node_vector_subtraction1.inputs[1].default_value[2] = 0.5
            node_vector_subtraction1.location = -535, 0

            node_normalize = group.nodes.new('ShaderNodeVectorMath')
            node_normalize.operation = 'NORMALIZE'
            node_normalize.location = -535, -245

            node_dot_product = group.nodes.new('ShaderNodeVectorMath')
            node_dot_product.operation = 'DOT_PRODUCT'
            node_dot_product.location = -340, -125

            node_multiply = group.nodes.new('ShaderNodeMixRGB')
            node_multiply.blend_type = 'MULTIPLY'
            node_multiply.inputs['Fac'].default_value = 1.0
            node_multiply.location = -145, -125

            node_vector_subtraction2 = group.nodes.new('ShaderNodeVectorMath')
            node_vector_subtraction2.operation = 'SUBTRACT'
            node_vector_subtraction2.location = 40, 0

            # link nodes together
            group.links.new(node_texture_coordinate.outputs['Generated'], node_vector_subtraction1.inputs[0])
            group.links.new(node_texture_coordinate.outputs['Normal'], node_normalize.inputs[0])
            group.links.new(node_vector_subtraction1.outputs['Vector'], node_dot_product.inputs[0])
            group.links.new(node_normalize.outputs['Vector'], node_dot_product.inputs[1])
            group.links.new(node_dot_product.outputs['Value'], node_multiply.inputs['Color1'])
            group.links.new(node_normalize.outputs['Vector'], node_multiply.inputs['Color2'])
            group.links.new(node_vector_subtraction1.outputs['Vector'], node_vector_subtraction2.inputs[0])
            group.links.new(node_multiply.outputs['Color'], node_vector_subtraction2.inputs[1])
            group.links.new(node_vector_subtraction2.outputs['Vector'], node_output.inputs['Vector'])

    # **************************************************************************************
    def __createBlenderVectorElementPowerNodeGroup():
        if bpy.data.node_groups.get('Vector-Element-Power') is None:
            debugPrint("createBlenderVectorElementPowerNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('Vector-Element-Power', -580, 0, 400, 0, False)
            group.inputs.new('NodeSocketFloat','Exponent')
            group.inputs.new('NodeSocketVectorDirection','Vector')
            group.outputs.new('NodeSocketVectorDirection','Vector')

            # create nodes
            node_separate_xyz = group.nodes.new('ShaderNodeSeparateXYZ')
            node_separate_xyz.location = -385, -140

            node_abs_x = group.nodes.new('ShaderNodeMath')
            node_abs_x.operation = 'ABSOLUTE'
            node_abs_x.location = -180, 180

            node_abs_y = group.nodes.new('ShaderNodeMath')
            node_abs_y.operation = 'ABSOLUTE'
            node_abs_y.location = -180, 0

            node_abs_z = group.nodes.new('ShaderNodeMath')
            node_abs_z.operation = 'ABSOLUTE'
            node_abs_z.location = -180, -180

            node_power_x = group.nodes.new('ShaderNodeMath')
            node_power_x.operation = 'POWER'
            node_power_x.location = 20, 180

            node_power_y = group.nodes.new('ShaderNodeMath')
            node_power_y.operation = 'POWER'
            node_power_y.location = 20, 0

            node_power_z = group.nodes.new('ShaderNodeMath')
            node_power_z.operation = 'POWER'
            node_power_z.location = 20, -180

            node_combine_xyz = group.nodes.new('ShaderNodeCombineXYZ')
            node_combine_xyz.location = 215, 0

            # link nodes together
            group.links.new(node_input.outputs['Vector'], node_separate_xyz.inputs[0])
            group.links.new(node_separate_xyz.outputs['X'], node_abs_x.inputs[0])
            group.links.new(node_separate_xyz.outputs['Y'], node_abs_y.inputs[0])
            group.links.new(node_separate_xyz.outputs['Z'], node_abs_z.inputs[0])
            group.links.new(node_abs_x.outputs['Value'], node_power_x.inputs[0])
            group.links.new(node_input.outputs['Exponent'], node_power_x.inputs[1])
            group.links.new(node_abs_y.outputs['Value'], node_power_y.inputs[0])
            group.links.new(node_input.outputs['Exponent'], node_power_y.inputs[1])
            group.links.new(node_abs_z.outputs['Value'], node_power_z.inputs[0])
            group.links.new(node_input.outputs['Exponent'], node_power_z.inputs[1])
            group.links.new(node_power_x.outputs['Value'], node_combine_xyz.inputs['X'])
            group.links.new(node_power_y.outputs['Value'], node_combine_xyz.inputs['Y'])
            group.links.new(node_power_z.outputs['Value'], node_combine_xyz.inputs['Z'])
            group.links.new(node_combine_xyz.outputs['Vector'], node_output.inputs[0])

    # **************************************************************************************
    def __createBlenderConvertToNormalsNodeGroup():
        if bpy.data.node_groups.get('Convert-To-Normals') is None:
            debugPrint("createBlenderConvertToNormalsNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('Convert-To-Normals', -490, 0, 400, 0, False)
            group.inputs.new('NodeSocketFloat','Vector Length')
            group.inputs.new('NodeSocketFloat','Smoothing')
            group.inputs.new('NodeSocketFloat','Strength')
            group.inputs.new('NodeSocketVectorDirection','Normal')
            group.outputs.new('NodeSocketVectorDirection','Normal')

            # create nodes
            node_power = group.nodes.new('ShaderNodeMath')
            node_power.operation = 'POWER'
            node_power.location = -290, 150

            node_colorramp = group.nodes.new('ShaderNodeValToRGB')
            node_colorramp.color_ramp.color_mode = 'RGB'
            node_colorramp.color_ramp.interpolation = 'EASE'
            node_colorramp.color_ramp.elements[0].color = (1, 1, 1, 1)
            node_colorramp.color_ramp.elements[1].color = (0, 0, 0, 1)
            node_colorramp.color_ramp.elements[1].position = 0.45
            node_colorramp.location = -95, 150

            node_bump = group.nodes.new('ShaderNodeBump')
            node_bump.inputs['Distance'].default_value = 0.02
            node_bump.location = 200, 0

            # link nodes together
            group.links.new(node_input.outputs['Vector Length'], node_power.inputs[0])
            group.links.new(node_input.outputs['Smoothing'], node_power.inputs[1])
            group.links.new(node_power.outputs['Value'], node_colorramp.inputs[0])
            group.links.new(node_input.outputs['Strength'], node_bump.inputs['Strength'])
            group.links.new(node_colorramp.outputs['Color'], node_bump.inputs['Height'])
            group.links.new(node_input.outputs['Normal'], node_bump.inputs['Normal'])
            group.links.new(node_bump.outputs['Normal'], node_output.inputs[0])

    # **************************************************************************************
    def __createBlenderConcaveWallsNodeGroup():
        if bpy.data.node_groups.get('Concave Walls') is None:
            debugPrint("createBlenderConcaveWallsNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('Concave Walls', -530, 0, 300, 0, False)
            group.inputs.new('NodeSocketFloat','Strength')
            group.inputs.new('NodeSocketVectorDirection','Normal')
            group.outputs.new('NodeSocketVectorDirection','Normal')

            # create nodes
            node_distance_to_center = group.nodes.new('ShaderNodeGroup')
            node_distance_to_center.node_tree = bpy.data.node_groups['Distance-To-Center']
            node_distance_to_center.location = (-340,105)

            node_vector_elements_power = group.nodes.new('ShaderNodeGroup')
            node_vector_elements_power.node_tree = bpy.data.node_groups['Vector-Element-Power']
            node_vector_elements_power.location = (-120,105)
            node_vector_elements_power.inputs['Exponent'].default_value = 4.0

            node_convert_to_normals = group.nodes.new('ShaderNodeGroup')
            node_convert_to_normals.node_tree = bpy.data.node_groups['Convert-To-Normals']
            node_convert_to_normals.location = (90,0)
            node_convert_to_normals.inputs['Strength'].default_value = 0.2
            node_convert_to_normals.inputs['Smoothing'].default_value = 0.3

            # link nodes together
            group.links.new(node_distance_to_center.outputs['Vector'], node_vector_elements_power.inputs['Vector'])
            group.links.new(node_vector_elements_power.outputs['Vector'], node_convert_to_normals.inputs['Vector Length'])
            group.links.new(node_input.outputs['Strength'], node_convert_to_normals.inputs['Strength'])
            group.links.new(node_input.outputs['Normal'], node_convert_to_normals.inputs['Normal'])
            group.links.new(node_convert_to_normals.outputs['Normal'], node_output.inputs['Normal'])

    # **************************************************************************************
    def __createBlenderFresnelNodeGroup():
        if bpy.data.node_groups.get('PBR-Fresnel-Roughness') is None:
            debugPrint("createBlenderFresnelNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('PBR-Fresnel-Roughness', -530, 0, 300, 0, False)
            group.inputs.new('NodeSocketFloatFactor','Roughness')
            group.inputs.new('NodeSocketFloat','IOR')
            group.inputs.new('NodeSocketVectorDirection','Normal')
            group.outputs.new('NodeSocketFloatFactor','Fresnel Factor')

            # create nodes
            node_fres = group.nodes.new('ShaderNodeFresnel')
            node_fres.location = (110,0)

            node_mix = group.nodes.new('ShaderNodeMixRGB')
            node_mix.location = (-80,-75)

            node_bump = group.nodes.new('ShaderNodeBump')
            node_bump.location = (-320,-172)
            # node_bump.hide = True

            node_geom = group.nodes.new('ShaderNodeNewGeometry')
            node_geom.location = (-320,-360)
            # node_geom.hide = True

            # link nodes together
            group.links.new(node_input.outputs['Roughness'],   node_mix.inputs['Fac'])       # Input Roughness -> Mix Fac
            group.links.new(node_input.outputs['IOR'],         node_fres.inputs['IOR'])      # Input IOR -> Fres IOR
            group.links.new(node_input.outputs['Normal'],      node_bump.inputs['Normal'])   # Input Normal -> Bump Normal
            group.links.new(node_bump.outputs['Normal'],       node_mix.inputs['Color1'])    # Bump Normal -> Mix Color1
            group.links.new(node_geom.outputs['Incoming'],     node_mix.inputs['Color2'])    # Geom Incoming -> Mix Colour2
            group.links.new(node_mix.outputs['Color'],         node_fres.inputs['Normal'])   # Mix Color -> Fres Normal
            group.links.new(node_fres.outputs['Fac'],          node_output.inputs['Fresnel Factor']) # Fres Fac -> Group Output Fresnel Factor

    # **************************************************************************************
    def __createBlenderReflectionNodeGroup():
        if bpy.data.node_groups.get('PBR-Reflection') is None:
            debugPrint("createBlenderReflectionNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('PBR-Reflection', -530, 0, 300, 0, True)
            group.inputs.new('NodeSocketShader','Shader')
            group.inputs.new('NodeSocketFloatFactor','Roughness')
            group.inputs.new('NodeSocketFloatFactor','Reflection')
            group.inputs.new('NodeSocketFloat','IOR')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            node_fresnel_roughness = group.nodes.new('ShaderNodeGroup')
            node_fresnel_roughness.node_tree = bpy.data.node_groups['PBR-Fresnel-Roughness']
            node_fresnel_roughness.location = (-290,145)

            node_mixrgb = group.nodes.new('ShaderNodeMixRGB')
            node_mixrgb.location = (-80,115)
            node_mixrgb.inputs['Color2'].default_value = (0.0, 0.0, 0.0, 1.0)

            node_mix_shader = group.nodes.new('ShaderNodeMixShader')
            node_mix_shader.location = (100,0)

            node_glossy = group.nodes.new('ShaderNodeBsdfGlossy')
            node_glossy.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0)
            node_glossy.location = (-290,-95)

            # link nodes together
            group.links.new(node_input.outputs['Shader'],       node_mix_shader.inputs[1])
            group.links.new(node_input.outputs['Roughness'],    node_fresnel_roughness.inputs['Roughness'])
            group.links.new(node_input.outputs['Roughness'],    node_glossy.inputs['Roughness'])
            group.links.new(node_input.outputs['Reflection'],   node_mixrgb.inputs['Color1'])
            group.links.new(node_input.outputs['IOR'],          node_fresnel_roughness.inputs['IOR'])
            group.links.new(node_input.outputs['Normal'],       node_fresnel_roughness.inputs['Normal'])
            group.links.new(node_input.outputs['Normal'],       node_glossy.inputs['Normal'])
            group.links.new(node_fresnel_roughness.outputs[0],  node_mixrgb.inputs[0])
            group.links.new(node_mixrgb.outputs[0],             node_mix_shader.inputs[0])
            group.links.new(node_glossy.outputs[0],             node_mix_shader.inputs[2])
            group.links.new(node_mix_shader.outputs[0],         node_output.inputs['Shader'])

    # **************************************************************************************
    def __createBlenderDielectricNodeGroup():
        if bpy.data.node_groups.get('PBR-Dielectric') is None:
            debugPrint("createBlenderDielectricNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('PBR-Dielectric', -530, 70, 500, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketFloatFactor','Roughness')
            group.inputs.new('NodeSocketFloatFactor','Reflection')
            group.inputs.new('NodeSocketFloatFactor','Transparency')
            group.inputs.new('NodeSocketFloat','IOR')
            group.inputs.new('NodeSocketVectorDirection','Normal')
            group.inputs['IOR'].default_value = 1.46
            group.inputs['IOR'].min_value = 0.0
            group.inputs['IOR'].max_value = 100.0
            group.inputs['Roughness'].default_value = 0.2
            group.inputs['Roughness'].min_value = 0.0
            group.inputs['Roughness'].max_value = 1.0
            group.inputs['Reflection'].default_value = 0.1
            group.inputs['Reflection'].min_value = 0.0
            group.inputs['Reflection'].max_value = 1.0
            group.inputs['Transparency'].default_value = 0.0
            group.inputs['Transparency'].min_value = 0.0
            group.inputs['Transparency'].max_value = 1.0

            node_diffuse = group.nodes.new('ShaderNodeBsdfDiffuse')
            node_diffuse.location = (-110,145)

            node_reflection = group.nodes.new('ShaderNodeGroup')
            node_reflection.node_tree = bpy.data.node_groups['PBR-Reflection']
            node_reflection.location = (100,115)

            node_power = group.nodes.new('ShaderNodeMath')
            node_power.operation = 'POWER'
            node_power.inputs[1].default_value = 2.0
            node_power.location = (-330,-105)

            node_glass = group.nodes.new('ShaderNodeBsdfGlass')
            node_glass.location = (100,-105)

            node_mix_shader = group.nodes.new('ShaderNodeMixShader')
            node_mix_shader.location = (300,5)

            # link nodes together
            group.links.new(node_input.outputs['Color'],        node_diffuse.inputs['Color'])
            group.links.new(node_input.outputs['Roughness'],    node_power.inputs[0])
            group.links.new(node_input.outputs['Reflection'],   node_reflection.inputs['Reflection'])
            group.links.new(node_input.outputs['IOR'],          node_reflection.inputs['IOR'])
            group.links.new(node_input.outputs['Normal'],       node_diffuse.inputs['Normal'])
            group.links.new(node_input.outputs['Normal'],       node_reflection.inputs['Normal'])
            group.links.new(node_power.outputs[0],              node_diffuse.inputs['Roughness'])
            group.links.new(node_power.outputs[0],              node_reflection.inputs['Roughness'])
            group.links.new(node_diffuse.outputs[0],            node_reflection.inputs['Shader'])
            group.links.new(node_reflection.outputs['Shader'],  node_mix_shader.inputs['Shader'])
            group.links.new(node_input.outputs['Color'],        node_glass.inputs['Color'])
            group.links.new(node_input.outputs['IOR'],          node_glass.inputs['IOR'])
            group.links.new(node_input.outputs['Normal'],       node_glass.inputs['Normal'])
            group.links.new(node_power.outputs[0],              node_glass.inputs['Roughness'])
            group.links.new(node_input.outputs['Transparency'], node_mix_shader.inputs[0])
            group.links.new(node_glass.outputs[0],              node_mix_shader.inputs[2])
            group.links.new(node_mix_shader.outputs['Shader'],  node_output.inputs['Shader'])

    # **************************************************************************************
    def __createBlenderLegoStandardNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Standard')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoStandardNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -250, 0, 250, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            if Options.instructionsLook:
                node_emission = BlenderMaterials.__nodeEmission(group.nodes, 0, 0)
                group.links.new(node_input.outputs['Color'],       node_emission.inputs['Color'])
                group.links.new(node_emission.outputs['Emission'], node_output.inputs['Shader'])
            else:
                node_dielectric = BlenderMaterials.nodeDielectric(group.nodes, 0.2, 0.1, 0.0, 1.46, 0, 0)

                # link nodes together
                group.links.new(node_input.outputs['Color'],       node_dielectric.inputs['Color'])
                group.links.new(node_input.outputs['Normal'],      node_dielectric.inputs['Normal'])
                group.links.new(node_dielectric.outputs['Shader'], node_output.inputs['Shader'])

    # **************************************************************************************
    def __createBlenderLegoTransparentNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Transparent')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoTransparentNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -250, 0, 250, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            if Options.instructionsLook:
                node_emission    = BlenderMaterials.__nodeEmission(group.nodes, 0, 0)
                node_transparent = BlenderMaterials.__nodeTransparent(group.nodes, 0, 100)
                node_mix1        = BlenderMaterials.__nodeMix(group.nodes, 0.5, 400, 100)
                node_light       = BlenderMaterials.__nodeLightPath(group.nodes, 200, 400)
                node_less        = BlenderMaterials.__nodeMath(group.nodes, 'LESS_THAN', 400, 400)
                node_mix2        = BlenderMaterials.__nodeMix(group.nodes, 0.5, 600, 300)
                
                node_output.location = (800,0)
                
                group.links.new(node_input.outputs['Color'],                node_emission.inputs['Color'])
                group.links.new(node_transparent.outputs[0],                node_mix1.inputs[1])
                group.links.new(node_emission.outputs['Emission'],          node_mix1.inputs[2])
                group.links.new(node_transparent.outputs[0],                node_mix2.inputs[1])
                group.links.new(node_mix1.outputs[0],                       node_mix2.inputs[2])
                group.links.new(node_light.outputs['Transparent Depth'],    node_less.inputs[0])
                group.links.new(node_less.outputs[0],                       node_mix2.inputs['Fac'])
                group.links.new(node_mix2.outputs[0],                       node_output.inputs['Shader'])
            else:
                node_dielectric = BlenderMaterials.nodeDielectric(group.nodes, 0.15, 0.1, 0.97, 1.46, 0, 0)

                # link nodes together
                group.links.new(node_input.outputs['Color'],       node_dielectric.inputs['Color'])
                group.links.new(node_input.outputs['Normal'],      node_dielectric.inputs['Normal'])
                group.links.new(node_dielectric.outputs['Shader'], node_output.inputs['Shader'])

    # **************************************************************************************
    def __createBlenderLegoRubberNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Rubber Solid')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoTransparentNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -250, 0, 250, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            node_dielectric = BlenderMaterials.nodeDielectric(group.nodes, 0.5, 0.07, 0.0, 1.52, 0, 0)

            # link nodes together
            group.links.new(node_input.outputs['Color'],       node_dielectric.inputs['Color'])
            group.links.new(node_input.outputs['Normal'],      node_dielectric.inputs['Normal'])
            group.links.new(node_dielectric.outputs['Shader'], node_output.inputs['Shader'])


    # **************************************************************************************
    def __createBlenderLegoRubberTranslucentNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Rubber Translucent')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoRubberTranslucentNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -250, 0, 250, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            node_dielectric = BlenderMaterials.nodeDielectric(group.nodes, 0.15, 0.1, 0.97, 1.46, 0, 0)

            # link nodes together
            group.links.new(node_input.outputs['Color'],       node_dielectric.inputs['Color'])
            group.links.new(node_input.outputs['Normal'],      node_dielectric.inputs['Normal'])
            group.links.new(node_dielectric.outputs['Shader'], node_output.inputs['Shader'])

    # **************************************************************************************
    def __createBlenderLegoEmissionNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Rubber Translucent')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoEmissionNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 90, 250, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketFloatFactor','Luminance')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            node_trans = BlenderMaterials.__nodeTranslucent(group.nodes, -242, 154)
            node_emit  = BlenderMaterials.__nodeEmission(group.nodes, -242, -23)
            node_mix   = BlenderMaterials.__nodeMix(group.nodes, 0.5, 0, 90)

            # link nodes together
            group.links.new(node_input.outputs['Color'],     node_trans.inputs['Color'])
            group.links.new(node_input.outputs['Normal'],    node_trans.inputs['Normal'])
            group.links.new(node_input.outputs['Luminance'], node_mix.inputs[0])
            group.links.new(node_trans.outputs[0],        node_mix.inputs[1])
            group.links.new(node_emit.outputs[0],         node_mix.inputs[2])
            group.links.new(node_mix.outputs[0],          node_output.inputs[0])

    # **************************************************************************************
    def __createBlenderLegoChromeNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Chrome')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoChromeNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 90, 250, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            node_glossyOne = BlenderMaterials.__nodeGlossy(group.nodes, (1,1,1,1), 0.03, 'GGX', -242, 154)
            node_glossyTwo = BlenderMaterials.__nodeGlossy(group.nodes, (1.0, 1.0, 1.0, 1.0), 0.03, 'BECKMANN', -242, -23)
            node_mix       = BlenderMaterials.__nodeMix(group.nodes, 0.01, 0, 90)

            # link nodes together
            group.links.new(node_input.outputs['Color'],  node_glossyOne.inputs['Color'])
            group.links.new(node_input.outputs['Normal'], node_glossyOne.inputs['Normal'])
            group.links.new(node_input.outputs['Normal'], node_glossyTwo.inputs['Normal'])
            group.links.new(node_glossyOne.outputs[0],    node_mix.inputs[1])
            group.links.new(node_glossyTwo.outputs[0],    node_mix.inputs[2])
            group.links.new(node_mix.outputs[0],          node_output.inputs[0])

    # **************************************************************************************
    def __createBlenderLegoPearlescentNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Pearlescent')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoPearlescentNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 90, 250, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            node_diffuse = BlenderMaterials.__nodeDiffuse(group.nodes, 0.0, -242, -23)
            node_glossy  = BlenderMaterials.__nodeGlossy(group.nodes, (1,1,1,1), 0.05, 'BECKMANN', -242, 154)
            node_mix     = BlenderMaterials.__nodeMix(group.nodes, 0.4, 0, 90)

            # link nodes together
            group.links.new(node_input.outputs['Color'],  node_diffuse.inputs['Color'])
            group.links.new(node_input.outputs['Color'],  node_glossy.inputs['Color'])
            group.links.new(node_input.outputs['Normal'], node_diffuse.inputs['Normal'])
            group.links.new(node_input.outputs['Normal'], node_glossy.inputs['Normal'])
            group.links.new(node_glossy.outputs[0],   node_mix.inputs[1])
            group.links.new(node_diffuse.outputs[0],  node_mix.inputs[2])
            group.links.new(node_mix.outputs[0],      node_output.inputs[0])

    # **************************************************************************************
    def __createBlenderLegoMetalNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Metal')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoMetalNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 90, 250, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            node_dielectric = BlenderMaterials.nodeDielectric(group.nodes, 0.05, 0.2, 0.0, 1.46, -242, 0)
            node_glossy = BlenderMaterials.__nodeGlossy(group.nodes, (1,1,1,1), 0.2, 'BECKMANN', -242, 154)
            node_mix = BlenderMaterials.__nodeMix(group.nodes, 0.4, 0, 90)

            # link nodes together
            group.links.new(node_input.outputs['Color'], node_glossy.inputs['Color'])
            group.links.new(node_input.outputs['Color'], node_dielectric.inputs['Color'])
            group.links.new(node_input.outputs['Normal'], node_glossy.inputs['Normal'])
            group.links.new(node_input.outputs['Normal'], node_dielectric.inputs['Normal'])
            group.links.new(node_glossy.outputs[0],     node_mix.inputs[1])
            group.links.new(node_dielectric.outputs[0], node_mix.inputs[2])
            group.links.new(node_mix.outputs[0],        node_output.inputs[0])

    # **************************************************************************************
    def __createBlenderLegoGlitterNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Glitter')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoGlitterNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 0, 410, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketColor','Glitter Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            node_glass   = BlenderMaterials.__nodeGlass(group.nodes, 0.05, 1.46, 'BECKMANN', -242, 154)
            node_glossy  = BlenderMaterials.__nodeGlossy(group.nodes, (1,1,1,1), 0.05, 'BECKMANN', -242, -23)
            node_diffuse = BlenderMaterials.__nodeDiffuse(group.nodes, 0.0, -12, -49)
            node_voronoi = BlenderMaterials.__nodeVoronoi(group.nodes, 100, -232, 310)
            node_gamma   = BlenderMaterials.__nodeGamma(group.nodes, 50, 0, 200)
            node_mixOne  = BlenderMaterials.__nodeMix(group.nodes, 0.05, 0, 90)
            node_mixTwo  = BlenderMaterials.__nodeMix(group.nodes, 0.5, 200, 90)

            # link nodes together
            group.links.new(node_input.outputs['Color'], node_glass.inputs['Color'])
            group.links.new(node_input.outputs['Glitter Color'], node_diffuse.inputs['Color'])
            group.links.new(node_input.outputs['Normal'], node_glass.inputs['Normal'])
            group.links.new(node_input.outputs['Normal'], node_glossy.inputs['Normal'])
            group.links.new(node_input.outputs['Normal'], node_diffuse.inputs['Normal'])
            group.links.new(node_glass.outputs[0],     node_mixOne.inputs[1])
            group.links.new(node_glossy.outputs[0],    node_mixOne.inputs[2])
            group.links.new(node_voronoi.outputs[0],   node_gamma.inputs[0])
            group.links.new(node_gamma.outputs[0],     node_mixTwo.inputs[0])
            group.links.new(node_mixOne.outputs[0],    node_mixTwo.inputs[1])
            group.links.new(node_diffuse.outputs[0],   node_mixTwo.inputs[2])
            group.links.new(node_mixTwo.outputs[0],    node_output.inputs[0])

    # **************************************************************************************
    def __createBlenderLegoSpeckleNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Speckle')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoSpeckleNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 0, 410, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketColor','Speckle Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            node_diffuseOne = BlenderMaterials.__nodeDiffuse(group.nodes, 0.0, -242, 131)
            node_glossy     = BlenderMaterials.__nodeGlossy(group.nodes, (0.333, 0.333, 0.333, 1.0), 0.2, 'BECKMANN', -242, -23)
            node_diffuseTwo = BlenderMaterials.__nodeDiffuse(group.nodes, 0.0, -12, -49)
            node_voronoi    = BlenderMaterials.__nodeVoronoi(group.nodes, 100, -232, 310)
            node_gamma      = BlenderMaterials.__nodeGamma(group.nodes, 20, 0, 200)
            node_mixOne     = BlenderMaterials.__nodeMix(group.nodes, 0.2, 0, 90)
            node_mixTwo     = BlenderMaterials.__nodeMix(group.nodes, 0.5, 200, 90)

            # link nodes together
            group.links.new(node_input.outputs['Color'], node_diffuseOne.inputs['Color'])
            group.links.new(node_input.outputs['Speckle Color'], node_diffuseTwo.inputs['Color'])
            group.links.new(node_input.outputs['Normal'], node_diffuseOne.inputs['Normal'])
            group.links.new(node_input.outputs['Normal'], node_glossy.inputs['Normal'])
            group.links.new(node_input.outputs['Normal'], node_diffuseTwo.inputs['Normal'])
            group.links.new(node_voronoi.outputs[0],       node_gamma.inputs[0])
            group.links.new(node_diffuseOne.outputs[0],    node_mixOne.inputs[1])
            group.links.new(node_glossy.outputs[0],        node_mixOne.inputs[2])
            group.links.new(node_gamma.outputs[0],         node_mixTwo.inputs[0])
            group.links.new(node_mixOne.outputs[0],        node_mixTwo.inputs[1])
            group.links.new(node_diffuseTwo.outputs[0],    node_mixTwo.inputs[2])
            group.links.new(node_mixTwo.outputs[0],        node_output.inputs[0])

    # **************************************************************************************
    def __createBlenderLegoMilkyWhiteNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Milky White')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoMilkyWhiteNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 0, 350, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            node_diffuse = BlenderMaterials.__nodeDiffuse(group.nodes, 0.0, -242, 90)
            node_trans   = BlenderMaterials.__nodeTranslucent(group.nodes, -242, -46)
            node_glossy  = BlenderMaterials.__nodeGlossy(group.nodes, (1,1,1,1), 0.5, 'BECKMANN', -42, -54)
            node_mixOne  = BlenderMaterials.__nodeMix(group.nodes, 0.4, -35, 90)
            node_mixTwo  = BlenderMaterials.__nodeMix(group.nodes, 0.2, 175, 90)

            # link nodes together
            group.links.new(node_input.outputs['Color'],  node_diffuse.inputs['Color'])
            group.links.new(node_input.outputs['Color'],  node_trans.inputs['Color'])
            group.links.new(node_input.outputs['Color'],  node_glossy.inputs['Color'])
            group.links.new(node_input.outputs['Normal'], node_diffuse.inputs['Normal'])
            group.links.new(node_input.outputs['Normal'], node_trans.inputs['Normal'])
            group.links.new(node_input.outputs['Normal'], node_glossy.inputs['Normal'])
            group.links.new(node_diffuse.outputs[0],  node_mixOne.inputs[1])
            group.links.new(node_trans.outputs[0],    node_mixOne.inputs[2])
            group.links.new(node_mixOne.outputs[0],   node_mixTwo.inputs[1])
            group.links.new(node_glossy.outputs[0],   node_mixTwo.inputs[2])
            group.links.new(node_mixTwo.outputs[0],   node_output.inputs[0])

    # **************************************************************************************
    def createBlenderNodeGroups():
        BlenderMaterials.__createBlenderDistanceToCenterNodeGroup()
        BlenderMaterials.__createBlenderVectorElementPowerNodeGroup()
        BlenderMaterials.__createBlenderConvertToNormalsNodeGroup()
        BlenderMaterials.__createBlenderConcaveWallsNodeGroup()
        # Based on ideas from https://www.youtube.com/watch?v=V3wghbZ-Vh4
        # "Create your own PBR Material [Fixed!]" by BlenderGuru
        BlenderMaterials.__createBlenderFresnelNodeGroup()
        BlenderMaterials.__createBlenderReflectionNodeGroup()
        BlenderMaterials.__createBlenderDielectricNodeGroup()
        BlenderMaterials.__createBlenderLegoStandardNodeGroup()
        BlenderMaterials.__createBlenderLegoTransparentNodeGroup()
        BlenderMaterials.__createBlenderLegoRubberNodeGroup()
        BlenderMaterials.__createBlenderLegoRubberTranslucentNodeGroup()
        BlenderMaterials.__createBlenderLegoEmissionNodeGroup()
        BlenderMaterials.__createBlenderLegoChromeNodeGroup()
        BlenderMaterials.__createBlenderLegoPearlescentNodeGroup()
        BlenderMaterials.__createBlenderLegoMetalNodeGroup()
        BlenderMaterials.__createBlenderLegoGlitterNodeGroup()
        BlenderMaterials.__createBlenderLegoSpeckleNodeGroup()
        BlenderMaterials.__createBlenderLegoMilkyWhiteNodeGroup()


# **************************************************************************************
def addSharpEdges(bm, geometry, filename):
    if geometry.edges:
        global globalWeldDistance
        epsilon = globalWeldDistance

        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        # Create kd tree for fast "find nearest points" calculation
        kd = mathutils.kdtree.KDTree(len(bm.verts))
        for i, v in enumerate(bm.verts):
            kd.insert(v.co, i)
        kd.balance()

        # Create edgeIndices dictionary, which is the list of edges as pairs of indicies into our bm.verts array
        edgeIndices = {}
        for ind, geomEdge in enumerate(geometry.edges):
            # Find index of nearest points in bm.verts to geomEdge[0] and geomEdge[1]
            edges0 = [index for (co, index, dist) in kd.find_range(geomEdge[0], epsilon)]
            edges1 = [index for (co, index, dist) in kd.find_range(geomEdge[1], epsilon)]

            #if (len(edges0) > 2):
            #    printWarningOnce("Found {1} vertices near {0} in file {2}".format(geomEdge[0], len(edges0), filename))
            #if (len(edges1) > 2):
            #    printWarningOnce("Found {1} vertices near {0} in file {2}".format(geomEdge[1], len(edges1), filename))

            for e0 in edges0:
                for e1 in edges1:
                    edgeIndices[(e0, e1)] = True
                    edgeIndices[(e1, e0)] = True

        # Find layer for bevel weights
        if 'BevelWeight' in bm.edges.layers.bevel_weight:
            bwLayer = bm.edges.layers.bevel_weight['BevelWeight']
        else:
            bwLayer = None

        # Find the appropriate mesh edges and make them sharp (i.e. not smooth)
        for meshEdge in bm.edges:
            v0 = meshEdge.verts[0].index
            v1 = meshEdge.verts[1].index
            if (v0, v1) in edgeIndices:
                # Make edge sharp
                meshEdge.smooth = False

                # Add bevel weight
                if bwLayer is not None:
                    meshEdge[bwLayer] = 1.0

# **************************************************************************************
def meshIsReusable(meshName, geometry):
    meshExists = meshName in bpy.data.meshes
    #debugPrint("meshIsReusable says {0} exists = {1}.".format(meshName, meshExists))
    if meshExists and not Options.overwriteExistingMeshes:
        mesh = bpy.data.meshes[meshName]

        #debugPrint("meshIsReusable testing")
        # A mesh loses it's materials information when it is no longer in use.
        # We must check the number of faces matches, otherwise we can't re-set the 
        # materials.
        if mesh.users == 0 and (len(mesh.polygons) != len(geometry.faces)):
            #debugPrint("meshIsReusable says no users and num faces changed.")
            return False
        
        # If options have changed (e.g. scale) we should not reuse the same mesh.
        if 'customMeshOptions' in mesh.keys():
            #debugPrint("meshIsReusable found custom options.")
            #debugPrint("mesh['customMeshOptions'] = {0}".format(mesh['customMeshOptions']))
            #debugPrint("Options.meshOptionsString() = {0}".format(Options.meshOptionsString()))
            if mesh['customMeshOptions'] == Options.meshOptionsString():
                #debugPrint("meshIsReusable found custom options - match OK.")
                return True
            #debugPrint("meshIsReusable found custom options - DON'T match.")
    return False

# **************************************************************************************
def addNodeToParentWithGroups(parentObject, groupNames, newObject):

    if not Options.flattenGroups:
        # Create groups as needed
        for groupName in groupNames:
            # The max length of a Blender node name appears to be 63 bytes when encoded as UTF-8. We make sure it fits.
            while len(groupName.encode("utf8")) > 63:
                groupName = groupName[:-1]
            
            # Check if we already have this node name, or if we need to create a new node
            groupObj = None
            for obj in bpy.data.objects:
                if (obj.name == groupName):
                    groupObj = obj
            if (groupObj is None):
                groupObj = bpy.data.objects.new(groupName, None)
                groupObj.parent = parentObject
                globalObjectsToAdd.append(groupObj)
            parentObject = groupObj

    newObject.parent = parentObject
    globalObjectsToAdd.append(newObject)

# **************************************************************************************
def createBlenderObjectsFromNode(node, localMatrix, name, realColourName=Options.defaultColour, blenderParentTransform=Math.identityMatrix, localToWorldSpaceMatrix=Math.identityMatrix, blenderNodeParent=None):
    """
    Creates a Blender Object for the node given and (recursively) for all it's children as required.
    Creates and optimises the mesh for each object too.
    """

    global globalBrickCount
    global globalObjectsToAdd
    global globalWeldDistance

    ob = None
    newMeshCreated = False

    if node.isBlenderObjectNode():
        ourColourName = LDrawNode.resolveColour(node.colourName, realColourName)
        meshName, geometry = node.getBlenderGeometry(ourColourName, name)
        if geometry.points:
            # Have we already cached this mesh?
            if Options.createInstances and hasattr(geometry, 'mesh'):
                mesh = geometry.mesh
            else:
                # Does this mesh already exist in Blender? 
                if meshIsReusable(meshName, geometry):
                    mesh = bpy.data.meshes[meshName]
                else:
                    # Create new mesh
                    # debugPrint("Creating Mesh for node {0}".format(node.filename))
                    mesh = bpy.data.meshes.new(meshName)

                    points = list(map((lambda p: p.to_tuple()), geometry.points))

                    mesh.from_pydata(points, [], geometry.faces)
                    mesh.validate()
                    mesh.update()
                    
                    # Set a custom parameter to record the options used to create this mesh
                    # Used for caching.
                    mesh['customMeshOptions'] = Options.meshOptionsString()

                    newMeshCreated = True

                # Create materials and assign material to each polygon
                if mesh.users == 0:
                    assert len(mesh.polygons) == len(geometry.faces)
                    assert len(geometry.faces) == len(geometry.faceColours)

                    for i, f in enumerate(mesh.polygons):
                        material = BlenderMaterials.getMaterial(geometry.faceColours[i])
                        if material is not None:
                            if mesh.materials.get(material.name) is None:
                                mesh.materials.append(material)
                            f.material_index = mesh.materials.find(material.name)
                        else:
                            printWarningOnce("Could not find material '{0}' in mesh '{1}'.".format(geometry.faceColours[i], name))

                # Cache mesh
                geometry.mesh = mesh
        else:
            mesh = None

        # Format a name for the Blender Object
        if Options.numberNodes:
            blenderName = str(globalBrickCount).zfill(5) + "_" + name
        else:
            blenderName = name
        globalBrickCount = globalBrickCount + 1

        # Create Blender Object
        ob = bpy.data.objects.new(blenderName, mesh)
        ob.matrix_local = blenderParentTransform * localMatrix

        # Mark object as transparent if any polygon is transparent
        ob["Lego.isTransparent"] = False
        if mesh is not None:
            for i, f in enumerate(mesh.polygons):
                material = BlenderMaterials.getMaterial(geometry.faceColours[i])
                if material is not None:
                    if "Lego.isTransparent" in material:
                        if material["Lego.isTransparent"]:
                            ob["Lego.isTransparent"] = True
                            break

        # Add any (LeoCAD) group nodes as parents of 'ob' (the new node), and as children of 'blenderNodeParent'. 
        # Also add all objects to 'globalObjectsToAdd'.
        addNodeToParentWithGroups(blenderNodeParent, node.groupNames, ob)

        # Node to which our children will be attached
        blenderNodeParent = ob
        blenderParentTransform = Math.identityMatrix

        if newMeshCreated:
            # For performance reasons we try to avoid using bpy.ops.* methods 
            # (e.g. we use bmesh.* operations instead). 
            # See discussion: http://blender.stackexchange.com/questions/7358/python-performance-with-blender-operators

            # Use bevel weights (added to sharp edges)
            ob.data.use_customdata_edge_bevel = True

            # Calculate what we need to do next
            recalculateNormals = node.file.isDoubleSided and (Options.resolveAmbiguousNormals == "guess")
            keepDoubleSided    = node.file.isDoubleSided and (Options.resolveAmbiguousNormals == "double")
            removeDoubles      = Options.removeDoubles and not keepDoubleSided

            bm = bmesh.new()
            bm.from_mesh(ob.data)
            bm.faces.ensure_lookup_table()
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()

            # Remove doubles
            if removeDoubles:
                bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=globalWeldDistance)

            # Recalculate normals
            if recalculateNormals:
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

            # Add sharp edges
            addSharpEdges(bm, geometry, name)

            bm.to_mesh(ob.data)
            bm.free()
            
            # Show the sharp edges in Edit Mode
            ob.data.show_edge_sharp = True

            # Scale for Gaps
            if Options.gaps and node.file.isPart:
                # Distance between gaps is controlled by Options.gapWidth
                # Gap height is set smaller than gapWidth since empirically, stacked bricks tend 
                # to be pressed more tightly together
                gapHeight = 0.33 * Options.gapWidth
                objScale = ob.scale
                dim = ob.dimensions

                # Checks whether the object isn't flat in a certain direction
                # to avoid division by zero.
                # Else, the scale factor is set proportional to the inverse of
                # the dimension so that the mesh shrinks a fixed distance
                # (determined by the gap_width and the scale of the object)
                # in every direction, creating a uniform gap.
                scaleFac = mathutils.Vector( (1.0, 1.0, 1.0) )
                if dim.x != 0:
                    scaleFac.x = 1 - Options.gapWidth * abs(objScale.x) / dim.x
                if dim.y != 0:
                    scaleFac.y = 1 - gapHeight        * abs(objScale.y) / dim.y
                if dim.z != 0:
                    scaleFac.z = 1 - Options.gapWidth * abs(objScale.z) / dim.z

                # A safety net: Don't distort the part too much (e.g. -ve scale would not look good)
                if scaleFac.x < 0.95:
                    scaleFac.x = 0.95
                if scaleFac.y < 0.95:
                    scaleFac.y = 0.95
                if scaleFac.z < 0.95:
                    scaleFac.z = 0.95

                # Scale all vertices in the mesh
                gapsScaleMatrix = mathutils.Matrix((
                    (scaleFac.x, 0.0,        0.0,        0.0),
                    (0.0,        scaleFac.y, 0.0,        0.0),
                    (0.0,        0.0,        scaleFac.z, 0.0),
                    (0.0,        0.0,        0.0,        1.0)
                ))
                mesh.transform(gapsScaleMatrix)

            # We would like to avoid using bpy.ops functions altogether since it 
            # slows down progressively as more objects are added to the scene, but 
            # we have no choice but to use it here (a) for smoothing and (b) for 
            # marking freestyle edges (no bmesh options exist currently). To minimise 
            # the performance drop, we add one object only to the scene, smooth it, 
            # then remove it again. Only at the end of the import process are all the 
            # objects properly added to the scene.

            # Temporarily add object to scene
            bpy.context.scene.objects.link(ob)

            # Select object
            ob.select = True
            bpy.context.scene.objects.active = ob

            # Smooth shading
            if Options.smoothShading:
                # Smooth the mesh
                bpy.ops.object.shade_smooth()

            # Mark all sharp edges as freestyle edges
            me = bpy.context.object.data
            for e in me.edges:
                e.use_freestyle_mark = e.use_edge_sharp

            # Deselect object
            ob.select = False
            bpy.context.scene.objects.active = None

            # Remove object from scene
            bpy.context.scene.objects.unlink(ob)

        # Add Bevel modifier to each instance
        if Options.addBevelModifier:
            if mesh:
                bevelModifier = ob.modifiers.new("Bevel", type='BEVEL')
                bevelModifier.width = 0.4 * Options.scale
                bevelModifier.segments = 4
                bevelModifier.profile = 0.5
                bevelModifier.limit_method = 'WEIGHT'
                bevelModifier.use_clamp_overlap = True

        # Add edge split modifier to each instance
        if Options.edgeSplit:
            if mesh:
                edgeModifier = ob.modifiers.new("Edge Split", type='EDGE_SPLIT')
                edgeModifier.use_edge_sharp = True
                edgeModifier.split_angle = math.radians(30.0)

        # Keep track of the global space bounding box, for positioning the object at the end
        # Notice that we do this after scaling from Options.gaps
        if Options.positionObjectOnGroundAtOrigin:
            if mesh and mesh.vertices:
                gPoints = list(map((lambda p: localToWorldSpaceMatrix * localMatrix * p.co), mesh.vertices))

                global globalMin
                global globalMax

                for p in gPoints:
                    globalMin[0] = min(p[0], globalMin[0])
                    globalMin[1] = min(p[1], globalMin[1])
                    globalMin[2] = min(p[2], globalMin[2])
                    globalMax[0] = max(p[0], globalMax[0])
                    globalMax[1] = max(p[1], globalMax[1])
                    globalMax[2] = max(p[2], globalMax[2])

        # Hide selection of studs
        if node.file.isStud:
            ob.hide_select = True
    else:
        blenderParentTransform = blenderParentTransform * localMatrix

    # Create children and parent them
    for childNode in node.file.childNodes:
        # Create sub-objects recursively
        childColourName = LDrawNode.resolveColour(childNode.colourName, realColourName)
        createBlenderObjectsFromNode(childNode, childNode.matrix, childNode.filename, childColourName, blenderParentTransform, localToWorldSpaceMatrix * localMatrix, blenderNodeParent)

    return ob

# **************************************************************************************
def addFileToCache(relativePath, name):
    """Loads and caches an LDraw file in the cache of files"""

    file = LDrawFile(relativePath, False, None, True)
    CachedFiles.addToCache(name, file)
    return True

# **************************************************************************************
def setupLineset(lineset):
    lineset.select_silhouette = True
    lineset.select_border = False
    lineset.select_contour = False
    lineset.select_suggestive_contour = False
    lineset.select_ridge_valley = False
    lineset.select_crease = False
    lineset.select_edge_mark = True
    lineset.select_external_contour = False
    lineset.select_material_boundary = False
    lineset.edge_type_combination = 'OR'
    lineset.edge_type_negation = 'INCLUSIVE'

    # Set line color
    lineset.linestyle.color = (0.0, 0.0, 0.0)
    
    # Set material to override color
    if 'LegoMaterial' not in lineset.linestyle.color_modifiers:
        lineset.linestyle.color_modifiers.new('LegoMaterial', 'MATERIAL')

    # Use rounded caps
    lineset.linestyle.caps = 'ROUND'

# **************************************************************************************
def setupInstructionsLook():
    scene = bpy.context.scene
    render = scene.render
    render.use_freestyle = True

    # Change camera to Orthographic
    scene.camera.data.type = 'ORTHO'

    # For Blender Render, set transparent background
    render.alpha_mode = 'TRANSPARENT'

    # Turn on cycles transparency
    scene.cycles.film_transparent = True

    # Increase max number of transparency bounces to at least 80
    # This avoids artefacts when multiple transparent objects are behind each other
    if scene.cycles.transparent_max_bounces < 80:
        scene.cycles.transparent_max_bounces = 80

    # Look for/create the render layers we are interested in:
    layerNames = list(map((lambda x: x.name), render.layers))
    if "SolidBricks" not in layerNames:
        bpy.ops.scene.render_layer_add()
        render.layers[-1].name = "SolidBricks"
        render.layers[-1].use = True
        layerNames.append("SolidBricks")
    solidLayer = layerNames.index("SolidBricks")

    if "TransparentBricks" not in layerNames:
        bpy.ops.scene.render_layer_add()
        render.layers[-1].name = "TransparentBricks"
        render.layers[-1].use = True
        layerNames.append("TransparentBricks")
    transLayer = layerNames.index("TransparentBricks")

    # Disable any render layers that are not needed
    for i in range(len(render.layers)):
        if i not in [solidLayer, transLayer]:
            render.layers[i].use = False

    # Enable two scene layers
    scene.layers[0] = True
    scene.layers[1] = True

    # Enable just the right scene layers in each of our two render layers
    length = len(render.layers[solidLayer].layers)
    for i in range(length):
        render.layers[solidLayer].layers[i] = (i == 0)
        render.layers[transLayer].layers[i] = (i == 1)

    # Move each part to appropriate scene layer
    for object in scene.objects:
        isTransparent = False
        if "Lego.isTransparent" in object:
            isTransparent = object["Lego.isTransparent"]

        # Turn on the appropriate layers
        if isTransparent:
            object.layers[1] = True
        else:
            object.layers[0] = True

        # Turn off all other layers as appropriate
        for i in range(length):
            if isTransparent:
                object.layers[i] = (i == 1)
            else:
                object.layers[i] = (i == 0)

    # Find or create linesets
    solidLineset = None
    transLineset = None

    for lineset in render.layers[solidLayer].freestyle_settings.linesets:
        if lineset.name == "LegoSolidLines":
            solidLineset = lineset

    for lineset in render.layers[transLayer].freestyle_settings.linesets:
        if lineset.name == "LegoTransLines":
            transLineset = lineset

    if solidLineset == None:
        render.layers[solidLayer].freestyle_settings.linesets.new("LegoSolidLines")
        solidLineset = render.layers[solidLayer].freestyle_settings.linesets[-1]
    if transLineset == None:
        render.layers[transLayer].freestyle_settings.linesets.new("LegoTransLines")
        transLineset = render.layers[transLayer].freestyle_settings.linesets[-1]

    setupLineset(solidLineset)
    setupLineset(transLineset)

    # Create Compositing Nodes
    scene.use_nodes = True
    #bpy.context.scene.node_tree.nodes
    if "Solid" in scene.node_tree.nodes:
        solidLayer = scene.node_tree.nodes["Solid"]
    else:
        solidLayer = scene.node_tree.nodes.new('CompositorNodeRLayers')
        solidLayer.name = "Solid"
        solidLayer.layer = 'SolidBricks'

    if "Trans" in scene.node_tree.nodes:
        transLayer = scene.node_tree.nodes["Trans"]
    else:
        transLayer = scene.node_tree.nodes.new('CompositorNodeRLayers')
        transLayer.name = "Trans"
        transLayer.layer = 'TransparentBricks'

    if "Z Combine" in scene.node_tree.nodes:
        zCombine = scene.node_tree.nodes["Z Combine"]
    else:
        zCombine = scene.node_tree.nodes.new('CompositorNodeZcombine')
    zCombine.use_alpha = True
    zCombine.use_antialias_z = True

    composite = scene.node_tree.nodes["Composite"]
    composite.location = (750, 400)
    zCombine.location = (500, 500)
    transLayer.location = (250, 300)
    solidLayer.location = (250, 600)

    links = scene.node_tree.links
    links.new(solidLayer.outputs[0], zCombine.inputs[0])
    links.new(solidLayer.outputs[2], zCombine.inputs[1])
    links.new(transLayer.outputs[0], zCombine.inputs[2])
    links.new(transLayer.outputs[2], zCombine.inputs[3])
    links.new(zCombine.outputs[0], composite.inputs[0])
    links.new(zCombine.outputs[1], composite.inputs[2])
    

# **************************************************************************************
def loadFromFile(context, filename, isFullFilepath=True):
    global globalContext
    globalContext = context

    # Make sure we have the latest configuration, including the latest ldraw directory 
    # and the colours derived from that.
    Configure()
    LegoColours()
    Math()

    if Configure.ldrawInstallDirectory == "":
        printError("Could not find LDraw Part Library")
        return None

    # Clear caches
    CachedFiles.clearCache()
    CachedGeometry.clearCache()
    BlenderMaterials.clearCache()
    Configure.warningSuppression = {}

    if Options.useLogoStuds:
        debugPrint("Loading stud files")
        # Load stud logo files into cache
        addFileToCache("stud-logo"   + Options.logoStudVersion + ".dat", "stud.dat")
        addFileToCache("stud2-logo"  + Options.logoStudVersion + ".dat", "stud2.dat")
        addFileToCache("stud6-logo"  + Options.logoStudVersion + ".dat", "stud6.dat")
        addFileToCache("stud6a-logo" + Options.logoStudVersion + ".dat", "stud6a.dat")
        addFileToCache("stud7-logo"  + Options.logoStudVersion + ".dat", "stud7.dat")
        addFileToCache("stud10-logo" + Options.logoStudVersion + ".dat", "stud10.dat")
        addFileToCache("stud13-logo" + Options.logoStudVersion + ".dat", "stud13.dat")
        addFileToCache("stud15-logo" + Options.logoStudVersion + ".dat", "stud15.dat")
        addFileToCache("stud20-logo" + Options.logoStudVersion + ".dat", "stud20.dat")
        addFileToCache("studa-logo"  + Options.logoStudVersion + ".dat", "studa.dat")

    # Load and parse file to create geometry
    filename = os.path.expanduser(filename)

    debugPrint("Loading files")
    node = LDrawNode(filename, isFullFilepath)
    node.load()
    # node.printBFC()

    # Fix top level rotation from LDraw coordinate space to Blender coordinate space
    node.file.geometry.points = list(map((lambda p: Math.rotationMatrix * p), node.file.geometry.points))
    node.file.geometry.edges  = list(map((lambda e: (Math.rotationMatrix * e[0], Math.rotationMatrix * e[1])), node.file.geometry.edges))
    for childNode in node.file.childNodes:
        childNode.matrix = Math.rotationMatrix * childNode.matrix

    # Switch to Object mode and deselect all
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')

    name = os.path.basename(filename)

    global globalBrickCount
    global globalObjectsToAdd
    global globalMin
    global globalMax

    globalBrickCount = 0
    globalObjectsToAdd = []

    # Keep track of our bounding box in global coordinate space
    globalMin = mathutils.Vector((sys.float_info.max, sys.float_info.max, sys.float_info.max))
    globalMax = mathutils.Vector((sys.float_info.min, sys.float_info.min, sys.float_info.min))

    debugPrint("Creating NodeGroups")
    BlenderMaterials.createBlenderNodeGroups()

    # Create Blender objects from the loaded file
    debugPrint("Creating Blender objects")
    rootOb = createBlenderObjectsFromNode(node, node.matrix, name)

    # Finally add each object to the scene
    debugPrint("Adding objects to scene")
    for ob in globalObjectsToAdd:
        bpy.context.scene.objects.link(ob)

    # Select the newly created root object
    rootOb.select = True
    bpy.context.scene.objects.active = rootOb

    # Centre object
    if Options.positionObjectOnGroundAtOrigin:
        if globalMin.x != sys.float_info.max:
            debugPrint("Centre object")
            vcentre = (globalMin + globalMax) * 0.5
            rootOb.location.x = rootOb.location.x - vcentre.x
            rootOb.location.y = rootOb.location.y - vcentre.y
            rootOb.location.z = rootOb.location.z - globalMin.z
            # bpy.ops.object.transform_apply(location=True)

    globalObjectsToAdd = []

    if Options.instructionsLook:
        setupInstructionsLook()

    debugPrint("Load Done")
    return rootOb
