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

Toby Nelson - toby@tnelson.demon.co.uk
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
    scale              = 0.04           # Size of the lego model to create. (0.04 is LeoCAD scale)
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
    gapWidth           = 0.04           # Width of gap between bricks (in Blender units)
    positionObjectOnGroundAtOrigin = True   # Centre the object at the origin, sitting on the z=0 plane
    flattenHierarchy   = True           # All parts are under the root object - no sub-models

    # We have the option of including the 'LEGO' logo on each stud
    useLogoStuds       = False          # Use the studs with the 'LEGO' logo on them
    logoStudVersion    = "4"            # Which version of the logo to use ("3" (flat), "4" (rounded) or "5" (subtle rounded))
    instanceStuds      = False          # Each stud is a new Blender object (slow)

    # LSynth (http://www.holly-wood.it/lsynth/tutorial-en.html) is a collection of parts used to render string, hoses, cables etc
    useLSynthParts     = True           # LSynth is used to render string, hoses etc.
    LSynthDirectory    = r""            # Full path to the lsynth parts (Defaults to <ldrawdir>/unofficial/lsynth if left blank)
    studLogoDirectory  = r""            # Optional full path to the stud logo parts (if not found in unofficial directory)


# **************************************************************************************
# Globals
globalBrickCount = 0
globalObjectsToAdd = []         # Blender objects to add to the scene
globalMin = None
globalMax = None
globalContext = None

# **************************************************************************************
def debugPrint(message):
    """Debug print with identification timestamp."""

    # Current timestamp (with milliseconds trimmed to two places)
    timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-4]

    message = "{0} [importldraw] {1}".format(timestamp, message)
    print("{0}".format(message))

    global globalContext
    if globalContext is not None:
        globalContext.report({'INFO'}, message)

# **************************************************************************************
def printWarningOnce(key, message=None):
    if message is None:
        message = key

    if key not in Configure.warningSuppression:
        debugPrint("WARNING: {0}".format(message))
        Configure.warningSuppression[key] = True

        global globalContext
        if globalContext is not None:
            globalContext.report({'WARNING'}, message)

# **************************************************************************************
def printError(message):
    debugPrint("ERROR: {0}".format(message))

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

        # Search for stud logo parts
        if Options.useLogoStuds and Options.studLogoDirectory != "":
            Configure.__appendPath(Options.studLogoDirectory)

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
                if os.path.exists(fullPathName):
                    return fullPathName

        return None


# **************************************************************************************
# **************************************************************************************
class CachedFiles:
    """Cached dictionary of LDrawFile objects keyed by filename"""

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

    def parse_face_line(self, parameters, cull, ccw):
        """Parse a face line"""

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

    def verify(self, face, numPoints):
        for i in face:
            assert i < numPoints
            assert i >= 0

    def appendGeometry(self, geometry, matrix, cull, invert):

        # Add face information
        pointCount = len(self.points)
        newIndices = []
        for index, face in enumerate(geometry.faces):
            # Gather points for this face (and transform points)
            newPoints = []
            for i in face:
                newPoints.append(matrix * geometry.points[i])

            # Add clockwise and/or anticlockwise sets of points as appropriate
            newFace = face.copy()
            for i in range(len(newFace)):
                newFace[i] += pointCount
            
            faceCCW = geometry.windingCCW[index] != invert
            faceCull = geometry.culling[index] and cull

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


# **************************************************************************************
# **************************************************************************************
class LDrawNode:
    """A node in the hierarchy. References one LDrawFile"""

    def __init__(self, filename, isFullFilepath, colourName=Options.defaultColour, matrix=Math.identityMatrix, bfcCull=True, bfcInverted=False, isLSynthPart=False, isSubPart=False, isRootNode=True):
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

    def isBlenderObjectNode(self):
        """
        Calculates if this node should become a Blender object.

        Some nodes will become objects in Blender, some will not.

        Typically nodes that reference a part become Blender Objects, but not subparts.
        """

        # The root node is always a Blender node
        if self.isRootNode:
            return True

        # General rule: We are a Blender object if we are a part or higher (ie. if we are not a subPart)
        isBON = not self.isSubPart

        # Exception #1 - If flattening the hierarchy, we only want parts (not models)
        if Options.flattenHierarchy:
            isBON = self.file.isPart

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

    def getBlenderGeometry(self, realColourName, accumCull=True, accumInvert=False):
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
        key = (self.filename, ourColourName, accumCull, accumInvert, self.bfcCull, self.bfcInverted)
        bakedGeometry = CachedGeometry.getCached(key)
        if bakedGeometry is None:
            # Start with a copy of our file's geometry
            assert len(self.file.geometry.faces) == len(self.file.geometry.faceColours)
            bakedGeometry = LDrawGeometry()
            bakedGeometry.appendGeometry(self.file.geometry, Math.identityMatrix, self.bfcCull, self.bfcInverted)

            # Replace the default colour
            bakedGeometry.faceColours = self.__bakeColours(bakedGeometry.faceColours, ourColourName)

            # Append each child's geometry
            for child in self.file.childNodes:
                assert child.file is not None
                if not child.isBlenderObjectNode():
                    childColourName = LDrawNode.resolveColour(child.colourName, ourColourName)
                    bg = child.getBlenderGeometry(childColourName, accumCull, accumInvert)
                    bakedGeometry.appendGeometry(bg, child.matrix, self.bfcCull, self.bfcInverted)

            CachedGeometry.addToCache(key, bakedGeometry)
        assert len(bakedGeometry.faces) == len(bakedGeometry.faceColours)
        return bakedGeometry


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

        # Extract just the filename, in lower case
        filename = filename.replace("\\", os.path.sep)
        name = os.path.basename(filename).lower()

        return name in ("stud.dat", "stud2.dat", "stud-logo3.dat", "stud2-logo3.dat", "stud-logo4.dat", "stud2-logo4.dat", "stud-logo5.dat", "stud2-logo5.dat")

    def __init__(self, filename, isFullFilepath, lines = None, isSubPart=False):
        """Loads an LDraw file (LDR, L3B, DAT or MPD)"""

        self.filename         = filename
        self.lines            = lines
        self.isPart           = False
        self.isSubPart        = isSubPart
        self.isStud           = LDrawFile.__isStud(filename)
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

        #debugPrint("Processing file {0}, isSubPart = {1}, found {2} lines".format(self.filename, self.isSubPart, len(self.lines)))

        for line in self.lines:
            parameters = line.strip().split()

            # Skip empty lines
            if len(parameters) == 0:
                continue
                
            # Pad with empty values to ease parsing
            while len(parameters) < 4:
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
                    if 'shortcut' in partType:
                        self.isSubPart = True

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

                    newNode = LDrawNode(new_filename, False, new_colourName, localMatrix, canCullChildNode, bfcInvertNext, processingLSynthParts, not self.isModel, False)
                    self.childNodes.append(newNode)

                # Parse a Face (either a triangle or a quadrilateral)
                elif parameters[0] == "3" or parameters[0] == "4":
                    if self.bfcCertified is None:
                        self.bfcCertified = False
                    if not self.bfcCertified or not bfcLocalCull:
                        printWarningOnce("Found double-sided polygons in file {0}".format(self.filename))
                        self.isDoubleSided = True

                    assert len(self.geometry.faces) == len(self.geometry.faceColours)
                    self.geometry.parse_face_line(parameters, self.bfcCertified and bfcLocalCull, bfcWindingCCW)
                    assert len(self.geometry.faces) == len(self.geometry.faceColours)

                bfcInvertNext = False

        #debugPrint("File {0} is part = {1}, is subPart = {2}, isModel = {3}".format(filename, self.isPart, isSubPart, self.isModel))


# **************************************************************************************
# **************************************************************************************
class BlenderMaterials:
    """Creates and stores a cache of materials for Blender"""

    __material_list = {}

    def __setBlenderRenderProperties(material, nodes, links, col):
        """Get Blender Internal Material Values."""
        material.diffuse_color = col["colour"]

        alpha = col["alpha"]
        if alpha < 1.0:
            material.use_transparency = True
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
        output.location = 190, -250

        links.new(input.outputs[0], output.inputs[0])
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
        nodes = material.node_tree.nodes
        links = material.node_tree.links

        # Remove any existing nodes
        for n in nodes:
            nodes.remove(n)

        if col is not None:
            BlenderMaterials.__setBlenderRenderProperties(material, nodes, links, col)

            colour = col["colour"] + (1.0,)

            if col["name"] == "Milky_White":
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
            return material

        BlenderMaterials.__createCyclesBasic(nodes, links, (1.0, 1.0, 0.0, 1.0), 1.0)
        return material

    def __nodeMix(nodes, factor, x, y):
        node = nodes.new('ShaderNodeMixShader')
        node.location = x, y
        node.inputs['Fac'].default_value = factor
        return node

    def __nodeOutput(nodes, x, y):
        node = nodes.new('ShaderNodeOutputMaterial')
        node.location = x, y
        return node

    def __nodeDiffuse(nodes, colour, roughness, x, y):
        node = nodes.new('ShaderNodeBsdfDiffuse')
        node.location = x, y
        node.inputs['Color'].default_value = colour
        node.inputs['Roughness'].default_value = roughness
        return node

    def __nodeGlass(nodes, colour, roughness, ior, distribution, x, y):
        node = nodes.new('ShaderNodeBsdfGlass')
        node.location = x, y
        node.distribution = distribution
        node.inputs['Color'].default_value = colour
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

    def __nodeTranslucent(nodes, colour, x, y):
        node = nodes.new('ShaderNodeBsdfTranslucent')
        node.location = x, y
        node.inputs['Color'].default_value = colour
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

    # Node setups based on https://rioforce.wordpress.com/2013/10/10/lego-materials-in-blender-cycles/
    def __createCyclesBasic(nodes, links, diffColour, alpha):
        """Basic Material for Cycles render engine."""

        mix = BlenderMaterials.__nodeMix(nodes, 0.05, 0, 90)
        out = BlenderMaterials.__nodeOutput(nodes, 290, 100)
        if alpha == 1.0:
            node = BlenderMaterials.__nodeDiffuse(nodes, diffColour, 0.0, -242, 154)
            fresnel = BlenderMaterials.__nodeFresnel(nodes, 1.46, -234, 260)
            links.new(fresnel.outputs[0], mix.inputs[0])
        else:
            node = BlenderMaterials.__nodeGlass(nodes, diffColour, 0.05, 1.46, 'BECKMANN', -242, 154)
            fresnel = BlenderMaterials.__nodeFresnel(nodes, 1.46, -234, 260)
            links.new(fresnel.outputs[0], mix.inputs[0])

        glossy = BlenderMaterials.__nodeGlossy(nodes, (1.0, 1.0, 1.0, 1.0), 0.05, 'BECKMANN', -242, -23)

        links.new(node.outputs[0],   mix.inputs[1])
        links.new(glossy.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0],    out.inputs[0])

    def __createCyclesEmission(nodes, links, diffColour, alpha, luminance):
        """Emission material for Cycles render engine."""

        trans = BlenderMaterials.__nodeTranslucent(nodes, diffColour, -242, 154)
        emit  = BlenderMaterials.__nodeEmission(nodes, -242, -23)
        mix   = BlenderMaterials.__nodeMix(nodes, luminance / 100, 0, 90)
        out   = BlenderMaterials.__nodeOutput(nodes, 290, 100)

        links.new(trans.outputs[0], mix.inputs[1])
        links.new(emit.outputs[0],  mix.inputs[2])
        links.new(mix.outputs[0],   out.inputs[0])

    def __createCyclesChrome(nodes, links, diffColour):
        """Chrome material for Cycles render engine."""

        glossyOne = BlenderMaterials.__nodeGlossy(nodes, diffColour, 0.03, 'GGX', -242, 154)
        glossyTwo = BlenderMaterials.__nodeGlossy(nodes, (1.0, 1.0, 1.0, 1.0), 0.03, 'BECKMANN', -242, -23)
        mix = BlenderMaterials.__nodeMix(nodes, 0.01, 0, 90)
        out = BlenderMaterials.__nodeOutput(nodes, 290, 100)

        links.new(glossyOne.outputs[0], mix.inputs[1])
        links.new(glossyTwo.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0],       out.inputs[0])

    def __createCyclesPearlescent(nodes, links, diffColour):
        """Pearlescent material for Cycles render engine."""

        diffuse = BlenderMaterials.__nodeDiffuse(nodes, diffColour, 0.0, -242, -23)
        glossy = BlenderMaterials.__nodeGlossy(nodes, diffColour, 0.05, 'BECKMANN', -242, 154)
        mix = BlenderMaterials.__nodeMix(nodes, 0.4, 0, 90)
        out = BlenderMaterials.__nodeOutput(nodes, 290, 100)

        links.new(glossy.outputs[0],  mix.inputs[1])
        links.new(diffuse.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0],     out.inputs[0])

    def __createCyclesMetal(nodes, links, diffColour):
        """Metal material for Cycles render engine."""

        diffuse = BlenderMaterials.__nodeDiffuse(nodes, diffColour, 0.0, -242, -23)
        glossy = BlenderMaterials.__nodeGlossy(nodes, diffColour, 0.2, 'BECKMANN', -242, 154)
        mix = BlenderMaterials.__nodeMix(nodes, 0.4, 0, 90)
        out = BlenderMaterials.__nodeOutput(nodes, 290, 100)

        links.new(glossy.outputs[0],  mix.inputs[1])
        links.new(diffuse.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0],     out.inputs[0])

    def __createCyclesGlitter(nodes, links, diffColour, glitterColour):
        """Glitter material for Cycles render engine."""

        glass   = BlenderMaterials.__nodeGlass(nodes, diffColour, 0.05, 1.46, 'BECKMANN', -242, 154)
        glossy  = BlenderMaterials.__nodeGlossy(nodes, (1.0, 1.0, 1.0, 1.0), 0.05, 'BECKMANN', -242, -23)
        diffuse = BlenderMaterials.__nodeDiffuse(nodes, LegoColours.lightenRGBA(glitterColour, 0.5), 0.0, -12, -49)
        voronoi = BlenderMaterials.__nodeVoronoi(nodes, 100, -232, 310)
        gamma   = BlenderMaterials.__nodeGamma(nodes, 50, 0, 200)
        mixOne  = BlenderMaterials.__nodeMix(nodes, 0.05, 0, 90)
        mixTwo  = BlenderMaterials.__nodeMix(nodes, 0.5, 200, 90)
        out = BlenderMaterials.__nodeOutput(nodes, 490, 100)

        links.new(glass.outputs[0],     mixOne.inputs[1])
        links.new(glossy.outputs[0],    mixOne.inputs[2])
        links.new(voronoi.outputs[0],   gamma.inputs[0])
        links.new(gamma.outputs[0],     mixTwo.inputs[0])
        links.new(mixOne.outputs[0],    mixTwo.inputs[1])
        links.new(diffuse.outputs[0],   mixTwo.inputs[2])
        links.new(mixTwo.outputs[0],    out.inputs[0])

    def __createCyclesSpeckle(nodes, links, diffColour, speckleColour):
        """Speckle material for Cycles render engine."""

        diffuseOne = BlenderMaterials.__nodeDiffuse(nodes, diffColour, 0.0, -242, 131)
        glossy     = BlenderMaterials.__nodeGlossy(nodes, (0.333, 0.333, 0.333, 1.0), 0.2, 'BECKMANN', -242, -23)
        diffuseTwo = BlenderMaterials.__nodeDiffuse(nodes, LegoColours.lightenRGBA(speckleColour, 0.5), 0.0, -12, -49)
        voronoi    = BlenderMaterials.__nodeVoronoi(nodes, 100, -232, 310)
        gamma      = BlenderMaterials.__nodeGamma(nodes, 20, 0, 200)
        mixOne     = BlenderMaterials.__nodeMix(nodes, 0.2, 0, 90)
        mixTwo     = BlenderMaterials.__nodeMix(nodes, 0.5, 200, 90)
        out = BlenderMaterials.__nodeOutput(nodes, 490, 100)

        links.new(voronoi.outputs[0],       gamma.inputs[0])
        links.new(diffuseOne.outputs[0],    mixOne.inputs[1])
        links.new(glossy.outputs[0],        mixOne.inputs[2])
        links.new(gamma.outputs[0],         mixTwo.inputs[0])
        links.new(mixOne.outputs[0],        mixTwo.inputs[1])
        links.new(diffuseTwo.outputs[0],    mixTwo.inputs[2])
        links.new(mixTwo.outputs[0],        out.inputs[0])

    def __createCyclesRubber(nodes, links, diffColour, alpha):
        """Rubber material colours for Cycles render engine."""

        mixTwo = BlenderMaterials.__nodeMix(nodes, 0.05, 200, 90)
        out    = BlenderMaterials.__nodeOutput(nodes, 490, 100)

        if alpha == 1.0:
            # Solid bricks
            diffuse = BlenderMaterials.__nodeDiffuse(nodes, diffColour, 0.0, -12, 154)
            glossy  = BlenderMaterials.__nodeGlossy(nodes, (1.0, 1.0, 1.0, 1.0), 0.2, 'BECKMANN', -12, -46)

            links.new(diffuse.outputs[0], mixTwo.inputs[1])
            links.new(glossy.outputs[0],  mixTwo.inputs[2])
        else:
            # Transparent bricks
            glass   = BlenderMaterials.__nodeGlass(nodes, diffColour, 0.4, 1.16, 'BECKMANN', -42, 154)
            glossy  = BlenderMaterials.__nodeGlossy(nodes, (1.0, 1.0, 1.0, 1.0), 0.2, 'GGX', -42, -26)
            fresnel = BlenderMaterials.__nodeFresnel(nodes, 1.46, -34, 260)
            links.new(fresnel.outputs[0], mixTwo.inputs[0])
            links.new(glass.outputs[0],   mixTwo.inputs[1])
            links.new(glossy.outputs[0],  mixTwo.inputs[2])

        links.new(mixTwo.outputs[0], out.inputs[0])

    def __createCyclesMilkyWhite(nodes, links, diffColour):
        """Milky White material for Cycles render engine."""

        diffuse = BlenderMaterials.__nodeDiffuse(nodes, diffColour, 0.0, -242, 90)
        trans   = BlenderMaterials.__nodeTranslucent(nodes, diffColour, -242, -46)
        glossy  = BlenderMaterials.__nodeGlossy(nodes, diffColour, 0.5, 'BECKMANN', -42, -54)
        mixOne  = BlenderMaterials.__nodeMix(nodes, 0.4, -35, 90)
        mixTwo  = BlenderMaterials.__nodeMix(nodes, 0.2, 175, 90)
        out     = BlenderMaterials.__nodeOutput(nodes, 390, 90)

        links.new(diffuse.outputs[0], mixOne.inputs[1])
        links.new(trans.outputs[0], mixOne.inputs[2])
        links.new(mixOne.outputs[0], mixTwo.inputs[1])
        links.new(glossy.outputs[0], mixTwo.inputs[2])
        links.new(mixTwo.outputs[0], out.inputs[0])

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
            "name": colourName,
            "colour": linearRGBA[0:3],
            "alpha": linearRGBA[3],
            "luminance": 0.0,
            "material": "BASIC"
        }

    def getMaterial(colourName):
        # If it's already in the cache, use that
        if (colourName in BlenderMaterials.__material_list):
            result = BlenderMaterials.__material_list[colourName]
            return result

        # Create new material
        blenderName = "Material_{0}".format(colourName)
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
def createBlenderObjectsFromNode(node, localMatrix, name, realColourName=Options.defaultColour, blenderParentTransform=Math.identityMatrix, localToWorldSpaceMatrix=Math.identityMatrix, blenderNodeParent=None):
    """
    Creates a Blender Object for the node given and (recursively) for all it's children as required.
    Creates and optimises the mesh for each object too.
    """

    global globalBrickCount
    global globalObjectsToAdd

    ob = None
    newMeshCreated = False

    if node.isBlenderObjectNode():
        # Have we cached this mesh already?
        ourColourName = LDrawNode.resolveColour(node.colourName, realColourName)
        geometry = node.getBlenderGeometry(ourColourName)
        if geometry.points:
            if Options.createInstances and hasattr(geometry, 'mesh'):
                mesh = geometry.mesh
            else:
                # Create new mesh
                # debugPrint("Creating Mesh for node {0}".format(node.filename))
                mesh = bpy.data.meshes.new("Mesh_{0}".format(name))

                points = list(map((lambda p: p.to_tuple()), geometry.points))

                mesh.from_pydata(points, [], geometry.faces)
                mesh.validate()
                mesh.update()

                newMeshCreated = True

                assert len(mesh.polygons) == len(geometry.faces)
                assert len(geometry.faces) == len(geometry.faceColours)

                # Create materials and assign material to each polygon
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
        ob.parent = blenderNodeParent

        # Node to which our children will be attached
        blenderNodeParent = ob
        blenderParentTransform = Math.identityMatrix

        # Don't add the object to the scene yet, just add it to a list
        globalObjectsToAdd.append(ob)

        if newMeshCreated:
            # For performance reasons we try to avoid using bpy.ops.* methods 
            # (e.g. we use bmesh.* operations instead). 
            # See discussion: http://blender.stackexchange.com/questions/7358/python-performance-with-blender-operators

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

            # Remove doubles
            if Options.removeDoubles and not node.file.isDoubleSided:
                bm = bmesh.new()
                bm.from_mesh(ob.data)
                bm.faces.ensure_lookup_table()
                bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.0005)
                bm.to_mesh(ob.data)

            # Smooth shading
            if Options.smoothShading:
                # We would like to avoid using bpy.ops functions altogether since it 
                # slows down progressively as more objects are added to the scene, but 
                # we have no choice but to use it here for smoothing (no bmesh option 
                # exists currently). To minimise the performance drop, we add one object
                # only to the scene, smooth it, then remove it again.
                # Only at the end of the import process are all the objects properly 
                # added to the scene.

                # Temporarily add object to scene
                bpy.context.scene.objects.link(ob)

                # Select object
                ob.select = True
                bpy.context.scene.objects.active = ob

                # Smooth the mesh
                bpy.ops.object.shade_smooth()

                # Deselect object
                ob.select = False
                bpy.context.scene.objects.active = None

                # Remove object from scene
                bpy.context.scene.objects.unlink(ob)

        # Add edge split modifier to each instance
        if Options.edgeSplit:
            if mesh:
                edges = ob.modifiers.new("Edge Split", type='EDGE_SPLIT')
                edges.split_angle = math.radians(30.0)

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
def addStudFileToCache(relativePath, name):
    """Loads and caches an LDraw file in the cache of files"""

    file = LDrawFile(relativePath, False, None, True)
    CachedFiles.addToCache(name, file)
    return True

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
        addStudFileToCache("stud-logo" + Options.logoStudVersion + ".dat", "stud.dat")
        addStudFileToCache("stud2-logo" + Options.logoStudVersion + ".dat", "stud2.dat")

    # Load and parse file to create geometry
    filename = os.path.expanduser(filename)

    debugPrint("Loading files")
    node = LDrawNode(filename, isFullFilepath)
    node.load()
    # node.printBFC()

    # Fix top level rotation from LDraw coordinate space to Blender coordinate space
    node.file.geometry.points = list(map((lambda p: Math.rotationMatrix * p), node.file.geometry.points))
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

    debugPrint("Load Done")
    return rootOb

# **************************************************************************************
if __name__ == "__main__":
    loadFromFile("3001.dat", False)
