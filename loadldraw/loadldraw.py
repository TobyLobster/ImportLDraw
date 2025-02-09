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

Accepts .io, .mpd, .ldr, .l3b, and .dat files.

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
import itertools
import operator
import zipfile
import tempfile
import base64
from dataclasses import dataclass

from pprint import pprint

# **************************************************************************************
def linkToScene(ob):
    if bpy.context.collection.objects.find(ob.name) < 0:
        bpy.context.collection.objects.link(ob)

# **************************************************************************************
def linkToCollection(collectionName, ob):
    global globalHasCollections

    # Add object to the appropriate collection
    if globalHasCollections:
        if bpy.data.collections[collectionName].objects.find(ob.name) < 0:
            bpy.data.collections[collectionName].objects.link(ob)
    else:
        bpy.data.groups[collectionName].objects.link(ob)

# **************************************************************************************
def unlinkFromScene(ob):
    if bpy.context.collection.objects.find(ob.name) >= 0:
        bpy.context.collection.objects.unlink(ob)

# **************************************************************************************
def selectObject(ob, recursive = False):
    ob.select_set(state=True)
    bpy.context.view_layer.objects.active = ob
    if recursive:
        bpy.ops.object.select_grouped(extend=True, type='CHILDREN_RECURSIVE')

# **************************************************************************************
def deselectObject(ob):
    ob.select_set(state=False)
    bpy.context.view_layer.objects.active = None

# **************************************************************************************
def addPlane(location, size):
    bpy.ops.mesh.primitive_plane_add(size=size, enter_editmode=False, location=location)

# **************************************************************************************
def useDenoising(scene, useDenoising):
    if hasattr(getLayers(scene)[0], "cycles"):
        getLayers(scene)[0].cycles.use_denoising = useDenoising

# **************************************************************************************
def getLayerNames(scene):
    return list(map((lambda x: x.name), getLayers(scene)))

# **************************************************************************************
def deleteEdge(bm, edge):
    bmesh.ops.delete(bm, geom=edge, context='EDGES')

# **************************************************************************************
def getLayers(scene):
    # Get the render/view layers we are interested in:
    return scene.view_layers

# **************************************************************************************
def getDiffuseColor(color):
    return color + (1.0,)

# **************************************************************************************
def ShowMessageBox(message = "", title = "Message Box", icon = 'INFO'):
    def draw(self, context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


# **************************************************************************************
# **************************************************************************************
class Options:
    """User Options"""

    # Full filepath to ldraw folder. If empty, some standard locations are attempted
    ldrawDirectory     = r""            # Full filepath to the ldraw parts library (searches some standard locations if left blank)
    instructionsLook   = False          # Set up scene to look like Lego Instruction booklets
    realScale          = 1              # Scale of lego to create (1 represents real world Lego scale)
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
    realGapWidth       = 0.0002         # Width of gap between bricks (in metres)
    curvedWalls        = True           # Manipulate normals to make surfaces look slightly concave
    importCameras      = True           # LeoCAD can specify cameras within the ldraw file format. Choose to load them or ignore them.
    positionObjectOnGroundAtOrigin = True   # Centre the object at the origin, sitting on the z=0 plane
    flattenHierarchy   = False          # All parts are under the root object - no sub-models
    minifigHierarchy   = True           # Parts of minifigs are automatically parented to each other in a hierarchy
    flattenGroups      = False          # All LEOCad groups are ignored - no groups
    usePrincipledShaderWhenAvailable = True  # Use the new principled shader
    scriptDirectory    = os.path.dirname( os.path.realpath(__file__) )

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
    bevelWidth         = 0.5            # Width of bevel

    addWorldEnvironmentTexture = True   # Add an environment texture
    addGroundPlane = True               # Add a ground plane
    setRenderSettings = True            # Set render percentage, denoising
    removeDefaultObjects = True         # Remove cube and lamp
    positionCamera = True               # Position the camera where so we get the whole object in shot
    cameraBorderPercent = 0.05          # Add a border gap around the positioned object (0.05 = 5%) for the rendered image

    def meshOptionsString():
        """These options change the mesh, so if they change, a new mesh needs to be cached"""

        return "_".join([str(Options.realScale),
                         str(Options.useUnofficialParts),
                         str(Options.instructionsLook),
                         str(Options.resolution),
                         str(Options.defaultColour),
                         str(Options.createInstances),
                         str(Options.useColourScheme),
                         str(Options.removeDoubles),
                         str(Options.smoothShading),
                         str(Options.gaps),
                         str(Options.realGapWidth),
                         str(Options.curvedWalls),
                         str(Options.flattenHierarchy),
                         str(Options.minifigHierarchy),
                         str(Options.useLogoStuds),
                         str(Options.logoStudVersion),
                         str(Options.instanceStuds),
                         str(Options.useLSynthParts),
                         str(Options.LSynthDirectory),
                         str(Options.studLogoDirectory),
                         str(Options.resolveAmbiguousNormals),
                         str(Options.addBevelModifier),
                         str(Options.bevelWidth)])

# **************************************************************************************
# Globals
globalBrickCount = 0
globalObjectsToAdd = []         # Blender objects to add to the scene
globalCamerasToAdd = []         # Camera data to add to the scene
globalContext = None
globalPoints = []
globalScaleFactor = 0.0004
globalWeldDistance = 0.0005
globalHasCollections = None

lightName = "Light"

# **************************************************************************************
# Dictionary with as keys the part numbers (without any extension for decorations)
# of pieces that have grainy slopes, and as values a set containing the angles (in
# degrees) of the face's normal to the horizontal plane. Use a tuple to represent a
# range within which the angle must lie.
globalSlopeBricks = {
    '962':{45},
    '2341':{-45},
    '2449':{-16},
    '2875':{45},
    '2876':{(40, 63)},
    '3037':{45},
    '3038':{45},
    '3039':{45},
    '3040':{45},
    '3041':{45},
    '3042':{45},
    '3043':{45},
    '3044':{45},
    '3045':{45},
    '3046':{45},
    '3048':{45},
    '3049':{45},
    '3135':{45},
    '3297':{63},
    '3298':{63},
    '3299':{63},
    '3300':{63},
    '3660':{-45},
    '3665':{-45},
    '3675':{63},
    '3676':{-45},
    '3678b':{24},
    '3684':{15},
    '3685':{16},
    '3688':{15},
    '3747':{-63},
    '4089':{-63},
    '4161':{63},
    '4286':{63},
    '4287':{-63},
    '4445':{45},
    '4460':{16},
    '4509':{63},
    '4854':{-45},
    '4856':{(-60, -70), -45},
    '4857':{45},
    '4858':{72},
    '4861':{45, 63},
    '4871':{-45},
    '4885':{72}, #blank
    '6069':{72, 45},
    '6153':{(60, 70), (26, 34)},
    '6227':{45},
    '6270':{45},
    '13269':{(40, 63)},
    '13548':{(45, 35)},
    '15571':{45},
    '18759':{-45},
    '22390':{(40, 55)}, #blank
    '22391':{(40, 55)},
    '22889':{-45},
    '28192':{45}, #blank
    '30180':{47},
    '30182':{45},
    '30183':{-45},
    '30249':{35},
    '30283':{-45},
    '30363':{72},
    '30373':{-24},
    '30382':{11, 45},
    '30390':{-45},
    '30499':{16},
    '32083':{45},
    '43708':{(64, 72)},
    '43710':{72, 45},
    '43711':{72, 45},
    '47759':{(40, 63)},
    '52501':{-45},
    '60219':{-45},
    '60477':{72},
    '60481':{24},
    '63341':{45},
    '72454':{-45},
    '92946':{45},
    '93348':{72},
    '95188':{65},
    '99301':{63},
    '303923':{45},
    '303926':{45},
    '304826':{45},
    '329826':{64},
    '374726':{-64},
    '428621':{64},
    '4162628':{17},
    '4195004':{45},
}

globalLightBricks = {
    '62930.dat':(1.0,0.373,0.059,1.0),
    '54869.dat':(1.0,0.052,0.017,1.0)
}

# Create a regular dictionary of parts with ranges of angles to check
margin = 5 # Allow 5 degrees either way to compensate for measuring inaccuracies
globalSlopeAngles = {}
for part, angles in globalSlopeBricks.items():
    globalSlopeAngles[part] = {(c-margin, c+margin) if type(c) is not tuple else (min(c)-margin,max(c)+margin) for c in angles}

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
        global globalScaleFactor

        # Rotation and scale matrices that convert LDraw coordinate space to Blender coordinate space
        Math.scaleMatrix = mathutils.Matrix((
                (globalScaleFactor, 0.0,               0.0,               0.0),
                (0.0,               globalScaleFactor, 0.0,               0.0),
                (0.0,               0.0,               globalScaleFactor, 0.0),
                (0.0,               0.0,               0.0,               1.0)
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
    tempDir = None

    def appendPath(path):
        if os.path.exists(path):
            Configure.searchPaths.append(path)

    def __setSearchPaths():
        Configure.searchPaths = []

        # Always search for parts in the 'models' folder
        Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "models"))
        Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "parts"))
        Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "parts", "s"))

        # Search for stud logo parts
        if Options.useLogoStuds and Options.studLogoDirectory != "":
            if Options.resolution == "Low":
                Configure.appendPath(os.path.join(Options.studLogoDirectory, "8"))
            Configure.appendPath(Options.studLogoDirectory)

        # Search unofficial parts
        if Options.useUnofficialParts:
            Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "unofficial", "parts"))

            if Options.resolution == "High":
                Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "unofficial", "p", "48"))
            elif Options.resolution == "Low":
                Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "unofficial", "p", "8"))
            Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "unofficial", "p"))

            # Add 'Tente' parts too
            Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "tente", "parts"))

            if Options.resolution == "High":
                Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "tente", "p", "48"))
            elif Options.resolution == "Low":
                Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "tente", "p", "8"))
            Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "tente", "p"))

        # Search LSynth parts
        if Options.useLSynthParts:
            if Options.LSynthDirectory != "":
                Configure.appendPath(Options.LSynthDirectory)
            else:
                Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "unofficial", "lsynth"))
            debugPrint("Use LSynth Parts requested")

        # Search official parts
        Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "parts"))
        if Options.resolution == "High":
            Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "p", "48"))
            debugPrint("High-res primitives selected")
        elif Options.resolution == "Low":
            Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "p", "8"))
            debugPrint("Low-res primitives selected")
        else:
            debugPrint("Standard-res primitives selected")

        Configure.appendPath(os.path.join(Configure.ldrawInstallDirectory, "p"))

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
                                            "C:\\Program Files\\Studio 2.0\\ldraw",
                                       ]
        elif Configure.isMac():
            ldrawPossibleDirectories = [
                                            "~/ldraw/",
                                            "/Applications/LDraw/",
                                            "/Applications/ldraw/",
                                            "/usr/local/share/ldraw",
                                            "/Applications/Studio 2.0/ldraw",
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

    def isDark(colour):
        R = colour[0]
        G = colour[1]
        B = colour[2]

        # Measure the perceived brightness of colour
        brightness = math.sqrt( 0.299*R*R + 0.587*G*G + 0.114*B*B )

        # Dark colours have white lines
        if brightness < 0.03:
            return True
        return False

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

    def __overwriteColour(index, sRGBColour):
        if index in LegoColours.colours:
            # Colour Space Management: Convert sRGB colour values to Blender's linear RGB colour space
            LegoColours.colours[index]["colour"] = LegoColours.sRGBtoLinearRGB(sRGBColour)

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

    def isFluorescentTransparent(colName):
        if (colName == "Trans_Neon_Orange"):
            return True
        if (colName == "Trans_Neon_Green"):
            return True
        if (colName == "Trans_Neon_Yellow"):
            return True
        if (colName == "Trans_Bright_Green"):
            return True
        return False

    def __init__(self):
        LegoColours.__readColourTable()


# **************************************************************************************
# **************************************************************************************
class FileSystem:
    """
    Reads text files in different encodings. Locates full filepath for a part.
    """

    # Takes a case-insensitive filepath and constructs a case sensitive version (based on an actual existing file)
    # See https://stackoverflow.com/questions/8462449/python-case-insensitive-file-name/8462613#8462613
    # (Note that https://stackoverflow.com/a/39140604 is slower)
    def pathInsensitive(path):
        """
        Get a case-insensitive path for use on a case sensitive system.

        >>> path_insensitive('/Home')
        '/home'
        >>> path_insensitive('/Home/chris')
        '/home/chris'
        >>> path_insensitive('/HoME/CHris/')
        '/home/chris/'
        >>> path_insensitive('/home/CHRIS')
        '/home/chris'
        >>> path_insensitive('/Home/CHRIS/.gtk-bookmarks')
        '/home/chris/.gtk-bookmarks'
        >>> path_insensitive('/home/chris/.GTK-bookmarks')
        '/home/chris/.gtk-bookmarks'
        >>> path_insensitive('/HOME/Chris/.GTK-bookmarks')
        '/home/chris/.gtk-bookmarks'
        >>> path_insensitive("/HOME/Chris/I HOPE this doesn't exist")
        "/HOME/Chris/I HOPE this doesn't exist"
        """
        try:
            result = CachedFilepaths.get(path)
            if result is None:
                result = FileSystem.__pathInsensitive(path) or path
                CachedFilepaths.add(path, result)
            return result
        except OSError:
            return path

    def __pathInsensitive(path):
        """
        Recursive part of path_insensitive to do the work.
        """

        if path == '' or os.path.exists(path):
            return path

        base = os.path.basename(path)  # may be a directory or a file
        dirname = os.path.dirname(path)

        suffix = ''
        if not base:  # dir ends with a slash?
            if len(dirname) < len(path):
                suffix = path[:len(path) - len(dirname)]

            base = os.path.basename(dirname)
            dirname = os.path.dirname(dirname)

        if not os.path.exists(dirname):
            debug_dirname = dirname
            dirname = FileSystem.__pathInsensitive(dirname)
            if not dirname:
                return

        # at this point, the directory exists but not the file

        try:  # we are expecting dirname to be a directory, but it could be a file
            files = CachedDirectoryFilenames.get(dirname)
            if files is None:
                files = os.listdir(dirname)
                CachedDirectoryFilenames.add(dirname, files)
        except OSError:
            return

        baselow = base.lower()
        try:
            basefinal = next(fl for fl in files if fl.lower() == baselow)
        except StopIteration:
            return

        if basefinal:
            return os.path.join(dirname, basefinal) + suffix
        else:
            return

    def __checkEncoding(filepath):
        """Check the encoding of a file for Endian encoding."""

        filepath = FileSystem.pathInsensitive(filepath)

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

        filepath = FileSystem.pathInsensitive(filepath)

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

    def locate(filename, rootPath = None):
        """Given a file name of an ldraw file, find the full path"""

        partName = filename.replace("\\", os.path.sep)
        partName = os.path.expanduser(partName)

        if rootPath is None:
            rootPath = os.path.dirname(filename)

        allSearchPaths = Configure.searchPaths[:]
        if rootPath not in allSearchPaths:
            allSearchPaths.append(rootPath)

        for path in allSearchPaths:
            fullPathName = os.path.join(path, partName)
            fullPathName = FileSystem.pathInsensitive(fullPathName)

            if os.path.exists(fullPathName):
                return fullPathName

        print("Could not find ", filename, " in paths ", allSearchPaths)

        return None


# **************************************************************************************
# **************************************************************************************
class Cached:
    """Simple cached dictionary of objects"""

    __cache = {}        # Dictionary

    def get(key):
        if key in __class__.__cache:
            return __class__.__cache[key]
        return None

    def getIndex(key):
        return list(__class__.__cache.keys()).index(key)

    def add(key, value):
        __class__.__cache[key] = value

    def clear():
        __class__.__cache = {}

# **************************************************************************************
# **************************************************************************************
class CachedTextureMaps(Cached):
    """Cached dictionary of texture map objects keyed by texture map name"""
    pass

# **************************************************************************************
# **************************************************************************************
class CachedFilepaths(Cached):
    """Cached actual filepaths keyed by requested path"""
    pass

# **************************************************************************************
# **************************************************************************************
class CachedDirectoryFilenames(Cached):
    """Cached dictionary of directory filenames keyed by directory path"""
    pass

# **************************************************************************************
# **************************************************************************************
class CachedGeometry(Cached):
    """Cached dictionary of LDrawGeometry objects"""
    pass

# **************************************************************************************
# **************************************************************************************
class CachedFiles:
    """Cached dictionary of LDrawFile objects keyed by filename"""

    __cache = {}        # Dictionary of exact filenames as keys, and file contents as values
    __lowercache = {}   # Dictionary of lowercase filenames as keys, and file contents as values

    def get(key):
        # Look for an exact match in the cache first
        if key in CachedFiles.__cache:
            return CachedFiles.__cache[key]

        # Look for a case-insensitive match next
        if key.lower() in CachedFiles.__lowercache:
            return CachedFiles.__lowercache[key.lower()]
        return None

    def add(key, value):
        CachedFiles.__cache[key] = value
        CachedFiles.__lowercache[key.lower()] = value

    def clear():
        CachedFiles.__cache = {}
        CachedFiles.__lowercache = {}


# **************************************************************************************
# **************************************************************************************
class FaceInfo:
    def __init__(self, faceColour, culling, windingCCW, isGrainySlopeAllowed, textureMap, parentDir):
        self.faceColour = faceColour
        self.culling = culling
        self.windingCCW = windingCCW
        self.isGrainySlopeAllowed = isGrainySlopeAllowed
        self.textureMap = textureMap
        self.parentDir = parentDir

# **************************************************************************************
# **************************************************************************************
class LDrawGeometry:
    """Stores the geometry for an LDrawFile"""

    def __init__(self):
        self.points = []
        self.uvs = []
        self.faces = []
        self.faceInfo = []
        self.edges = []
        self.edgeIndices = []

    def signed_angle(a, b, normal):
        # See https://stackoverflow.com/a/33920320
        s = a.cross(b).dot(normal)
        c = a.dot(b)
        return math.degrees(math.atan2(s, c))

    def applyTextureMap(self, textureMap, newPoints, debug):
        # TODO: Is this right or should it default to (0,0)'s?
        newUVs = [None] * len(newPoints)

        if not textureMap:
            return newUVs

        if debug:
            print("!!! textureMap=", textureMap)

        pt1 = mathutils.Vector( (textureMap.x1, textureMap.y1, textureMap.z1) )
        pt2 = mathutils.Vector( (textureMap.x2, textureMap.y2, textureMap.z2) )
        pt3 = mathutils.Vector( (textureMap.x3, textureMap.y3, textureMap.z3) )

        # Pre-calculate useful values
        len_p1p2 = (pt2 - pt1).length
        len_p1p3 = (pt3 - pt1).length

        if textureMap.projType == 'PLANAR':
            n1 = (pt2 - pt1).normalized()
            n2 = (pt3 - pt1).normalized()
        elif textureMap.projType == 'CYLINDRICAL':
            n1 = (pt2 - pt1).normalized()
        elif textureMap.projType == 'SPHERICAL':
            # take the cross product of the two vectors extending from pt2 to get a third vector n3 at right angles to those.
            n3 = (pt1 - pt2).cross(pt3 - pt2).normalized()
            n2 = (pt1 - pt2).cross(n3).normalized()

        for i in range(len(newPoints)):
            # Get the point in question (scaling the point back to original ldraw size), just for the purposes of UV coordinate calculation
            pt = newPoints[i]

            if textureMap.projType == 'PLANAR':
                # Calculate U
                if len_p1p2 > 1e-8:
                    u = math.fabs((pt1 - pt).dot(n1)) / len_p1p2
                else:
                    u = 0.0

                # Calculate V
                if len_p1p3 > 1e-8:
                    v = math.fabs((pt1 - pt).dot(n2)) / len_p1p3
                else:
                    v = 0.0

            elif textureMap.projType == 'CYLINDRICAL':
                # Calculate U
                distanceToPlane = (pt1 - pt).dot(n1)
                ptOnPlane       = pt - distanceToPlane * n1
                u  = LDrawGeometry.signed_angle(ptOnPlane - pt1, pt3 - pt1, -n1)
                u /= textureMap.a   # U is normalised
                u += 0.5            # U is centred

                # Calculate V
                if len_p1p2 > 1e-8:
                    v = math.fabs(distanceToPlane) / len_p1p2
                    v = 1-v
                else:
                    v = 0.0

            elif textureMap.projType == 'SPHERICAL':
                # Calculate U
                distanceToPlane = (pt - pt1).dot(n3)
                ptOnPlane       = pt - distanceToPlane * n3

                u  = LDrawGeometry.signed_angle(ptOnPlane - pt1, pt2 - pt1, n3)
                u /= textureMap.a   # U is normalised
                u += 0.5            # U is centred

                n0 = (pt - pt1).cross(n3).normalized()
                temp = LDrawGeometry.signed_angle(pt1 - pt, n3, -n0)
                v = temp / textureMap.b
                if debug and i == 0:
                    print("!!!! pt1=", pt1, "pt3=", pt3, "n0=", n0, "n3=", n3, "pt=", pt, " temp", temp, "(u,v)=", u, v)

                # This is V calculation according to the spec, but no-one uses it
                # Calculate V
                #distanceToPlane = (pt - pt1).dot(n2)
                #ptOnPlane       = pt - distanceToPlane * n2

                #v  = LDrawGeometry.signed_angle(ptOnPlane - pt1, pt2 - pt1, n2)
                #v /= textureMap.b   # V is normalised
                #v += 0.5            # V is centred

            else:
                # Unknown UV projection type
                u = 0.0
                v = 0.0

            #print("!!!! point=", pt, "(u,v)=", u, v)

            # Convert to Blender's UV system (which has a UV origin at the bottom left of the texture image, where LDraw uses the standard top left) and store
            blenderUV = mathutils.Vector( (u, 1-v) )
            newUVs[i] = blenderUV

        return newUVs

    def parseFace(self, parameters, cull, ccw, isGrainySlopeAllowed, textureMap, parentDir):
        """Parse a face from parameters"""

        num_points = int(parameters[0])
        colourName = parameters[1]

        # Add points
        newPoints = []
        for i in range(num_points):
            pt = mathutils.Vector( (float(parameters[i * 3 + 2]),
                                    float(parameters[i * 3 + 3]),
                                    float(parameters[i * 3 + 4])) )
            blenderPos = Math.scaleMatrix @ pt
            newPoints.append(blenderPos)

        # Fix "bowtie" quadrilaterals (see http://wiki.ldraw.org/index.php?title=LDraw_technical_restrictions#Complex_quadrilaterals)
        if num_points == 4:
            nA = (newPoints[1] - newPoints[0]).cross(newPoints[2] - newPoints[0])
            nB = (newPoints[2] - newPoints[1]).cross(newPoints[3] - newPoints[1])
            nC = (newPoints[3] - newPoints[2]).cross(newPoints[0] - newPoints[2])
            if (nA.dot(nB) < 0):
                newPoints[2], newPoints[3] = newPoints[3], newPoints[2]
                newUVs[2], newUVs[3] = newUVs[3], newUVs[2]
            elif (nB.dot(nC) < 0):
                newPoints[2], newPoints[1] = newPoints[1], newPoints[2]
                newUVs[2], newUVs[1] = newUVs[1], newUVs[2]

        pointCount = len(self.points)
        newFace = list(range(pointCount, pointCount + num_points))
        self.points.extend(newPoints)
        self.faces.append(newFace)
        self.faceInfo.append(FaceInfo(colourName, cull, ccw, isGrainySlopeAllowed, textureMap, parentDir))

    def parseEdge(self, parameters):
        """Parse an edge from parameters"""

        colourName = parameters[1]
        if colourName == "24":
            blenderPos1 = Math.scaleMatrix @ mathutils.Vector( (float(parameters[2]),
                                                                float(parameters[3]),
                                                                float(parameters[4])) )
            blenderPos2 = Math.scaleMatrix @ mathutils.Vector( (float(parameters[5]),
                                                                float(parameters[6]),
                                                                float(parameters[7])) )
            self.edges.append((blenderPos1, blenderPos2))

    def verify(self, face, numPoints):
        for i in face:
            assert i < numPoints
            assert i >= 0

# Old code to apply a texture map to a file, making a copy of it...
#if self.textureMap:
#    # Take a shallow copy of the LDrawFile
#    self.file = copy.copy(self.file)
#
#    # Apply textureMap to the file.
#    # Any faces without an existing texture map are texture mapped.
#    assert len(self.file.geometry.faces) == len(self.file.geometry.faceInfo)
#    for i in range(len(self.file.geometry.faces)):
#        faceInfo = self.file.geometry.faceInfo[i]
#        face = self.file.geometry.faces[i]
#        if not faceInfo.imageFilename:
#            realPoints = [self.file.geometry.points[i] for i in face]
#            realUVs = self.file.geometry.applyTextureMap(self.textureMap, realPoints)
#            j = 0
#            for i in face:
#                self.file.geometry.uvs[i] = realUVs[j]
#                j += 1
#        faceInfo.imageFilename = self.textureMap.imageFilename

    def appendGeometry(self, geometry, matrix, isStud, isStudLogo, parentMatrix, cull, invert, textureMap, textureMapMatrix, topLevelNode):
        global globalScaleFactor

        combinedMatrix = parentMatrix @ matrix
        isReflected = combinedMatrix.determinant() < 0.0
        reflectStudLogo = isStudLogo and isReflected

        # Transform the texture map into local space of the points
        if textureMap:
            localSpaceTextureMap = textureMap.transform(textureMapMatrix.inverted())
        else:
            localSpaceTextureMap = None

        fixedMatrix = matrix.copy()
        if reflectStudLogo:
            fixedMatrix = matrix @ Math.reflectionMatrix
            invert = not invert

        # Add texture map (UVs)
        # First add all dummy UV values
        pointCount = 0
        for face in geometry.faces:
            pointCount += len(face)
        geometry.uvs = [None] * pointCount

        # Create UVs for every vertex in every face
        for index, face in enumerate(geometry.faces):
            faceInfo = geometry.faceInfo[index]

            newPoints = []
            newUVs = []
            # Gather points in LDraw space for this face (for UV generation)
            for i in face:
                newPoints.append(geometry.points[i] / globalScaleFactor)
            if faceInfo.textureMap:
                if topLevelNode:
                    transformedTextureMap = faceInfo.textureMap.transform(Math.rotationMatrix)
                else:
                    transformedTextureMap = faceInfo.textureMap
                newUVs = geometry.applyTextureMap(transformedTextureMap, newPoints, False)
            else:
                #if localSpaceTextureMap:
                #    print("!!!! Applying localSpaceTextureMap=", localSpaceTextureMap)
                #    for pt in newPoints:
                #        print("!!!! Applying to point=", pt)
                newUVs = geometry.applyTextureMap(localSpaceTextureMap, newPoints, True if localSpaceTextureMap else False)
                #if localSpaceTextureMap:
                #    print("!!!! Applied localSpaceTextureMap=", localSpaceTextureMap)

            j = 0
            for i in face:
                geometry.uvs[i] = newUVs[j]
                j += 1

        # Append face information
        pointCount = len(self.points)
        newFaceInfo = []
        for index, face in enumerate(geometry.faces):
            # Gather points for this face (and transform points)
            newPoints = []
            newUVs    = []
            for i in face:
                newPoints.append(fixedMatrix @ geometry.points[i])
                newUVs.append(geometry.uvs[i])

            # Add clockwise and/or anticlockwise sets of points as appropriate
            newFace = face.copy()
            for i in range(len(newFace)):
                newFace[i] += pointCount

            faceInfo = copy.copy(geometry.faceInfo[index])
            faceCCW = faceInfo.windingCCW != invert
            faceCull = faceInfo.culling and cull

            if not faceInfo.textureMap:
                faceInfo.textureMap = textureMap

            # If we are going to resolve ambiguous normals by "best guess" we will let
            # Blender calculate that for us later. Just cull with arbitrary winding for now.
            if not faceCull:
                if Options.resolveAmbiguousNormals == "guess":
                    faceCull = True

            if faceCCW or not faceCull:
                self.points.extend(newPoints)
                self.uvs.extend(newUVs)
                self.faces.append(newFace)

                newFaceInfo.append(FaceInfo(faceInfo.faceColour, True, True, not isStud and faceInfo.isGrainySlopeAllowed, faceInfo.textureMap, faceInfo.parentDir))
                self.verify(newFace, len(self.points))

            if not faceCull:
                newFace = newFace.copy()
                pointCount += len(newPoints)
                for i in range(len(newFace)):
                    newFace[i] += len(newPoints)

            if not faceCCW or not faceCull:
                # Reverse the order of the new points and the UVs
                self.points.extend(newPoints[::-1])
                self.uvs.extend(newUVs[::-1])
                self.faces.append(newFace)

                newFaceInfo.append(FaceInfo(faceInfo.faceColour, True, True, not isStud and faceInfo.isGrainySlopeAllowed, faceInfo.textureMap, faceInfo.parentDir))
                self.verify(newFace, len(self.points))

        self.faceInfo.extend(newFaceInfo)
        assert len(self.faces) == len(self.faceInfo)

        # Append edge information
        newEdges = []
        for edge in geometry.edges:
            newEdges.append( (fixedMatrix @ edge[0], fixedMatrix @ edge[1]) )
        self.edges.extend(newEdges)


# **************************************************************************************
# **************************************************************************************
class LDrawNode:
    """A node in the hierarchy. References one LDrawFile"""

    def __init__(self, filename, isFullFilepath, parentDir, colourName=Options.defaultColour, matrix=Math.identityMatrix, bfcCull=True, bfcInverted=False, isLSynthPart=False, isSubPart=False, isRootNode=True, groupNames=[], textureMap=None):
        self.filename       = filename
        self.isFullFilepath = isFullFilepath
        self.parentDir      = parentDir
        self.matrix         = matrix
        self.colourName     = colourName
        self.bfcInverted    = bfcInverted
        self.bfcCull        = bfcCull
        self.file           = None
        self.isLSynthPart   = isLSynthPart
        self.isSubPart      = isSubPart
        self.isRootNode     = isRootNode
        self.groupNames     = groupNames.copy()
        self.textureMap     = textureMap

    def look_at(obj_camera, target, up_vector):
        bpy.context.view_layer.update()

        loc_camera = obj_camera.matrix_world.to_translation()

        #print("CamLoc = " + str(loc_camera[0]) + "," + str(loc_camera[1]) + "," + str(loc_camera[2]))
        #print("TarLoc = " + str(target[0]) + "," + str(target[1]) + "," + str(target[2]))
        #print("UpVec  = " + str(up_vector[0]) + "," + str(up_vector[1]) + "," + str(up_vector[2]))

        # back vector is a vector pointing from the target to the camera
        back = loc_camera - target
        back.normalize()

        # If our back and up vectors are very close to pointing the same way (or opposite), choose a different up_vector
        if (abs(back.dot(up_vector)) > 0.9999):
            up_vector=mathutils.Vector((0.0,0.0,1.0))
            if (abs(back.dot(up_vector)) > 0.9999):
                up_vector=mathutils.Vector((1.0,0.0,0.0))

        right = up_vector.cross(back)
        right.normalize()
        up = back.cross(right)
        up.normalize()

        row1 = [   right.x,   up.x,   back.x, loc_camera.x ]
        row2 = [   right.y,   up.y,   back.y, loc_camera.y ]
        row3 = [   right.z,   up.z,   back.z, loc_camera.z ]
        row4 = [       0.0,    0.0,      0.0,          1.0 ]

        #bpy.ops.mesh.primitive_ico_sphere_add(location=loc_camera+up,size=0.1)
        #bpy.ops.mesh.primitive_cylinder_add(location=loc_camera+back,radius = 0.1, depth=0.2)
        #bpy.ops.mesh.primitive_cone_add(location=loc_camera+right,radius1=0.1, radius2=0, depth=0.2)

        obj_camera.matrix_world = mathutils.Matrix((row1, row2, row3, row4))
        #print(obj_camera.matrix_world)

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
        self.file = CachedFiles.get(self.filename)
        if self.file is None:
            # Not in cache, so load file
            self.file = LDrawFile(self.filename, self.isFullFilepath, self.parentDir, None, self.isSubPart)
            assert self.file is not None

            CachedFiles.add(self.filename, self.file)

        # Load any children
        for child in self.file.childNodes:
            child.load()

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

    def getBlenderGeometry(self, realColourName, basename, textureMap, textureMapMatrix, topLevelNode, parentMatrix=Math.identityMatrix, accumCull=True, accumInvert=False):
        """
        Returns the geometry for the Blender Object at this node.

        It accumulates the geometry of itself with all the geometry of it's children
        recursively (specifically - those children that are not Blender Object nodes).

        The result will become a single mesh in Blender.
        """

        print("NODE=", self.filename)

        assert self.file is not None

        accumCull = accumCull and self.bfcCull
        accumInvert = accumInvert != self.bfcInverted

        ourColourName = LDrawNode.resolveColour(self.colourName, realColourName)
        code = LDrawNode.getBFCCode(accumCull, accumInvert, self.bfcCull, self.bfcInverted)
        meshName = "Mesh_{0}_{1}{2}".format(basename, ourColourName, code)
        if textureMap:
            tmKey = textureMap.name()
            CachedTextureMaps.add(tmKey, textureMap)
            meshName += "_tex" + str(CachedTextureMaps.getIndex(tmKey))
        else:
            tmKey = None

        key = (self.filename, ourColourName, accumCull, accumInvert, self.bfcCull, self.bfcInverted, tmKey)
        bakedGeometry = CachedGeometry.get(key)
        if bakedGeometry is None:
            combinedMatrix = parentMatrix @ self.matrix

            # Start with a copy of our file's geometry
            assert len(self.file.geometry.faces) == len(self.file.geometry.faceInfo)
            bakedGeometry = LDrawGeometry()

            bakedGeometry.appendGeometry(self.file.geometry, Math.identityMatrix, self.file.isStud, self.file.isStudLogo, combinedMatrix, self.bfcCull, self.bfcInverted, textureMap, textureMapMatrix, topLevelNode)

            # Replace the default colour 16 in our faceColours list with a specific colour
            for faceInfo in bakedGeometry.faceInfo:
                faceInfo.faceColour = LDrawNode.resolveColour(faceInfo.faceColour, ourColourName)

            # Append each child's geometry
            for child in self.file.childNodes:
                assert child.file is not None
                if not child.isBlenderObjectNode():
                    childColourName = LDrawNode.resolveColour(child.colourName, ourColourName)

                    if child.textureMap:
                        childTextureMap         = child.textureMap
                        childTextureMapMatrix   = child.matrix
                        print("!!!! hELLO, childTextureMapMatrix=", childTextureMapMatrix)
                    else:
                        childTextureMap         = textureMap
                        childTextureMapMatrix   = textureMapMatrix

                    childMeshName, bg = child.getBlenderGeometry(childColourName, basename, childTextureMap, childTextureMapMatrix, False, combinedMatrix, accumCull, accumInvert)

                    isStud = child.file.isStud
                    isStudLogo = child.file.isStudLogo

                    bakedGeometry.appendGeometry(bg, child.matrix, isStud, isStudLogo, combinedMatrix, self.bfcCull, self.bfcInverted, childTextureMap, childTextureMapMatrix, topLevelNode=False)

            CachedGeometry.add(key, bakedGeometry)
        assert len(bakedGeometry.faces) == len(bakedGeometry.faceInfo)
        return (meshName, bakedGeometry)


# **************************************************************************************
# **************************************************************************************
class LDrawCamera:
    """Data about a camera"""

    def __init__(self):
        self.vert_fov_degrees = 30.0
        self.near             = 0.01
        self.far              = 100.0
        self.position         = mathutils.Vector((0.0, 0.0, 0.0))
        self.target_position  = mathutils.Vector((1.0, 0.0, 0.0))
        self.up_vector        = mathutils.Vector((0.0, 1.0, 0.0))
        self.name             = "Camera"
        self.orthographic     = False
        self.hidden           = False

    def createCameraNode(self):
        camData = bpy.data.cameras.new(self.name)
        camera = bpy.data.objects.new(self.name, camData)

        # Add to scene
        camera.location = self.position
        camera.data.sensor_fit = 'VERTICAL'
        camera.data.angle = self.vert_fov_degrees * 3.1415926 / 180.0
        camera.data.clip_end = self.far
        camera.data.clip_start = self.near
        camera.hide_set(self.hidden)
        self.hidden = False

        if self.orthographic:
            dist_target_to_camera = (self.position - self.target_position).length
            camera.data.ortho_scale = dist_target_to_camera / 1.92
            camera.data.type = 'ORTHO'
            self.orthographic = False
        else:
            camera.data.type = 'PERSP'

        linkToScene(camera)
        LDrawNode.look_at(camera, self.target_position, self.up_vector)
        return camera


# **************************************************************************************
# **************************************************************************************
@dataclass
class TextureMap:
    def __init__(self, imageFilename, startOrNext, projType, virtualFullFilepath, x1, y1, z1, x2, y2, z2, x3, y3, z3, a = None, b = None):
        self.imageFilename = imageFilename
        self.startOrNext = startOrNext
        self.projType = projType
        # TODO: Document virtualFilepath
        self.virtualFullFilepath = virtualFullFilepath
        self.x1 = x1
        self.y1 = y1
        self.z1 = z1
        self.x2 = x2
        self.y2 = y2
        self.z2 = z2
        self.x3 = x3
        self.y3 = y3
        self.z3 = z3
        self.a = a
        self.b = b

    def transform(self, matrix):
        pt1 = matrix @ mathutils.Vector((self.x1, self.y1, self.z1))
        pt2 = matrix @ mathutils.Vector((self.x2, self.y2, self.z2))
        pt3 = matrix @ mathutils.Vector((self.x3, self.y3, self.z3))

        return TextureMap(self.imageFilename, self.startOrNext, self.projType, self.virtualFullFilepath,
                          pt1.x, pt1.y, pt1.z,
                          pt2.x, pt2.y, pt2.z,
                          pt3.x, pt3.y, pt3.z,
                          self.a, self.b)

    def name(self):
        return f'TextureMap("{self.imageFilename}","{self.startOrNext}","{self.projType}","{self.virtualFullFilepath}", ({self.x1} {self.y1} {self.z1})  ({self.x2} {self.y2} {self.z2})  ({self.x3} {self.y3} {self.z3})   {self.a} {self.b}'

    def __repr__(self):
        return f'TextureMap("{self.imageFilename}","{self.startOrNext}","{self.projType}","{self.virtualFullFilepath}", ({self.x1} {self.y1} {self.z1})  ({self.x2} {self.y2} {self.z2})  ({self.x3} {self.y3} {self.z3})   {self.a} {self.b}'

# **************************************************************************************
# **************************************************************************************
class BFC:
    def __init__(self):
        self.localCull  = True
        self.windingCCW = True
        self.invertNext = False

# **************************************************************************************
# **************************************************************************************
class LDrawFile:
    """Stores the contents of a single LDraw file.
    Specifically this represents an IO, LDR, L3B, DAT or one '0 FILE' section of an MPD.
    Splits up an MPD file into '0 FILE' sections and caches them."""

    def __loadLegoFile(self, filepath, isFullFilepath, parentDir):
        # Resolve full filepath if necessary
        if isFullFilepath is False:
            result = FileSystem.locate(filepath, parentDir)
            if result is None:
                printWarningOnce("Missing file {0}".format(filepath))
                return False
            filepath = result

        if os.path.splitext(filepath)[1] == ".io":
            # Check if the file is encrypted (password protected)
            is_encrypted = False
            zf = zipfile.ZipFile(filepath)
            for zinfo in zf.infolist():
                is_encrypted |= zinfo.flag_bits & 0x1
            if is_encrypted:
                ShowMessageBox("Oops, this .io file is password protected", "Password protected files are not supported", 'ERROR')
                return False

            # Get a temporary directory. Store the TemporaryDirectory object in Configure so it's scope lasts long enough
            Configure.tempDir = tempfile.TemporaryDirectory()
            directory_to_extract_to = Configure.tempDir.name

            # Decompress to temporary directory
            with zipfile.ZipFile(filepath, 'r') as zip_ref:
                zip_ref.extractall(directory_to_extract_to)

            # It's the 'model.ldr' file we want to use
            filepath = os.path.join(directory_to_extract_to, "model.ldr")

            # Add the subdirectories of the directory to the search paths
            Configure.appendPath(os.path.join(directory_to_extract_to, "CustomParts"))
            Configure.appendPath(os.path.join(directory_to_extract_to, "CustomParts", "parts"))

            if Options.resolution == "High":
                Configure.appendPath(os.path.join(directory_to_extract_to, "CustomParts", "p", "48"))
            elif Options.resolution == "Low":
                Configure.appendPath(os.path.join(directory_to_extract_to, "CustomParts", "p", "8"))
            Configure.appendPath(os.path.join(directory_to_extract_to, "CustomParts", "p"))
            Configure.appendPath(os.path.join(directory_to_extract_to, "CustomParts", "s"))
            Configure.appendPath(os.path.join(directory_to_extract_to, "CustomParts", "s", "s"))

        self.virtualFullFilepath = filepath

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
        currentSectionType = ""
        foundEnd = False

        for line in lines:
            parameters = line.strip().split()
            if len(parameters) > 2:
                if parameters[0] == "0" and parameters[1] == "FILE":
                    # Finish previous section
                    if foundEnd == False:
                        endLine = lineCount
                        if endLine > startLine:
                            sections.append((sectionFilename, lines[startLine:endLine], currentSectionType))

                    # Start new section
                    startLine = lineCount
                    foundEnd = False
                    currentSectionType = parameters[1]
                    sectionFilename = " ".join(parameters[2:])

                elif parameters[0] == "0" and parameters[1] == "!DATA":
                    # Finish previous section
                    if foundEnd == False:
                        endLine = lineCount
                        if endLine > startLine:
                            sections.append((sectionFilename, lines[startLine:endLine], currentSectionType))

                    # Start new section
                    startLine = lineCount
                    foundEnd = False
                    currentSectionType = parameters[1]
                    sectionFilename = " ".join(parameters[2:])

                elif parameters[0] == "0" and parameters[1] == "NOFILE":
                    # End section
                    endLine = lineCount
                    foundEnd = True
                    sections.append((sectionFilename, lines[startLine:endLine, currentSectionType]))
                    currentSectionType = ""
            lineCount += 1

        if foundEnd == False:
            # End final section
            endLine = lineCount
            if endLine > startLine:
                sections.append((sectionFilename, lines[startLine:endLine], currentSectionType))

        if len(sections) == 0:
            return False

        # First section is the main one
        self.filename = sections[0][0]
        self.lines = sections[0][1]

        parentDir = os.path.dirname(filepath)

        # Remaining sections are loaded into the cached files
        for (sectionFilename, lines, sectionType) in sections[1:]:
            if sectionType == "FILE":
                # Load FILE section
                textureMap = self.textureMaps[-1] if self.textureMaps else None
                file = LDrawFile(sectionFilename, False, parentDir, lines, False)
                assert file is not None
            elif sectionType == "!DATA":
                # Load binary !DATA from lines
                data = ""
                for line in lines:
                    parameters = line.strip().split()
                    if len(parameters) > 2:
                        if parameters[0] == "0":
                            if parameters[1] == "!:":
                                data += parameters[2]
                try:
                    # Decode the base64 text into binary bytes
                    file = base64.b64decode(data)

                    file_name, file_extension = os.path.splitext(sectionFilename)
                    if file_extension.lower() == '.png':
                        # Decode PNG data bytes into a Blender Image
                        file = LDrawFile.__image_from_data(sectionFilename, file)
                except Exception as e:
                    file = None
                    printWarningOnce(f"Embedded file '{sectionFilename}' could not be decoded. Exception: {e}")


            # Cache section
            if file:
                CachedFiles.add(sectionFilename, file)

        return True

    def __image_from_data(img_name, data):
        # See https://blender.stackexchange.com/a/240141
        # Create image, width and height are dummy values
        img = bpy.data.images.new(img_name, 8, 8)

        # Set packed file data
        img.pack(data=data, data_len=len(data))

        # Switch to file source so it uses the packed file
        img.source = 'FILE'

        return img


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
            "teton.dat",        # TENTE
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
            "studtente-logo.dat"    # TENTE
             )

    def __isStudLogo(filename):
        """Is this file a stud logo?"""

        # Extract just the filename, in lower case
        filename = filename.replace("\\", os.path.sep)
        name = os.path.basename(filename).lower()

        return name in ("logo3.dat", "logo4.dat", "logo5.dat", "logotente.dat")

    def __removeTextureMap(self, virtualFullEndFilepath = None):
        if self.textureMaps:
            # Check the 'END' TEXMAP is in the same file as the 'START' TEXMAP...
            if virtualFullEndFilepath == self.textureMaps[-1].virtualFullFilepath:
                del self.textureMaps[-1]

    def __removeIfNextTexture(self):
        if self.textureMaps:
            if self.textureMaps[-1].startOrNext == 'NEXT':
                del self.textureMaps[-1]

    def __getNextParameter(self, line):
        line = line.strip()         # skip spaces
        if not line:
            return (None, None)

        result = ""
        inQuotedString = False
        first = True
        while line:
            if line[0:1] == r'\\"' or line[0:1] == r'\\\\':
                # Backslash signifies a literal character next
                # Skip the backslash and add the next character
                line = line[1:]
            elif line[0] == r'"':
                # Handle initial and final quote
                if first:
                    # found start of a quoted string
                    inQuotedString = True
                    line = line[1:]
                    first = False
                    continue
                elif inQuotedString:
                    # found end of a quoted string
                    line = line[1:]
                    break
            elif line[0] == ' ':
                if not inQuotedString:
                    break

            if line:
                # Add current character to result
                result += line[0]
                line = line[1:]
            first = False

        return (line, result)

    def __parseGeometryLine(self, line, parameters, restOfLine, bfc, processingLSynthParts, currentGroupNames, isGrainySlopeAllowed, parentDir):
        # Ignore the FALLBACK section of the TEXMAP
        if self.inTexMapFallbackSection:
            return bfc

        # Parses commands 1,2,3,4,5 only. ie. files, lines, and faces.
        # This is used for texture mapped geometry too.

        if self.bfcCertified is None:
            self.bfcCertified = False

        self.isModel = (not self.isPart) and (not self.isSubPart)

        # Parse a file reference
        if parameters[0] == "1":
            (x, y, z, a, b, c, d, e, f, g, h, i) = map(float, parameters[2:14])
            (x, y, z) = Math.scaleMatrix @ mathutils.Vector((x, y, z))
            localMatrix = mathutils.Matrix( ((a, b, c, x), (d, e, f, y), (g, h, i, z), (0, 0, 0, 1)) )

            new_filename = restOfLine[14].strip()
            new_colourName = parameters[1]

            det = localMatrix.determinant()
            if det < 0:
                bfc.invertNext = not bfc.invertNext
            canCullChildNode = (self.bfcCertified or self.isModel) and bfc.localCull and (det != 0)

            if new_filename != "":
                textureMap = self.textureMaps[-1] if self.textureMaps else None
                newNode = LDrawNode(new_filename, False, parentDir, new_colourName, localMatrix, canCullChildNode, bfc.invertNext, processingLSynthParts, not self.isModel, False, currentGroupNames, textureMap)
                self.childNodes.append(newNode)
            else:
                printWarningOnce("In file '{0}', the line '{1}' is not formatted corectly (ignoring).".format(self.virtualFullFilepath, line))

        # Parse an edge
        elif parameters[0] == "2":
            self.geometry.parseEdge(parameters)
            # Remove any temporary ('NEXT' type) texture map after each geometry
            self.__removeIfNextTexture()

        # Parse a face (either a triangle or a quadrilateral)
        elif parameters[0] == "3" or parameters[0] == "4":
            if self.bfcCertified is None:
                self.bfcCertified = False
            if not self.bfcCertified or not bfc.localCull:
                printWarningOnce("Found double-sided polygons in file {0}".format(self.filename))
                self.isDoubleSided = True

            assert len(self.geometry.faces) == len(self.geometry.faceInfo)

            # get current texture map, if any
            textureMap = self.textureMaps[-1] if self.textureMaps else None
            self.geometry.parseFace(parameters, self.bfcCertified and bfc.localCull, bfc.windingCCW, isGrainySlopeAllowed, textureMap, parentDir)
            assert len(self.geometry.faces) == len(self.geometry.faceInfo)
            # Remove any temporary ('NEXT' type) texture map after each geometry
            self.__removeIfNextTexture()
        elif parameters[0] == "5":
            # Optional line, which we ignore except to cancel any current texture map with NEXT type
            # Remove any temporary ('NEXT' type) texture map after each geometry
            self.__removeIfNextTexture()

        bfc.invertNext = False
        return bfc

    def __init__(self, filename, isFullFilepath, parentDir, lines = None, isSubPart=False):
        """Loads an LDraw file (IO, LDR, L3B, DAT or MPD)"""

        global globalCamerasToAdd
        global globalScaleFactor

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
        self.isModel          = False
        self.textureMaps      = []
        self.inTexMapFallbackSection = False

        isGrainySlopeAllowed = not self.isStud

        if self.lines is None:
            # Load the file into self.lines
            if not self.__loadLegoFile(self.filename, isFullFilepath, parentDir):
                return
        else:
            # We are loading a section of our parent document, so full filepath is combined with the parent directory
            self.virtualFullFilepath = os.path.join(parentDir, filename)

        # BFC = Back face culling. The rules are arcane and complex, but at least
        #       it's kind of documented: http://www.ldraw.org/article/415.html
        bfc = BFC()
        processingLSynthParts = False
        camera = LDrawCamera()

        currentGroupNames = []

        #debugPrint("Processing file {0}, isSubPart = {1}, found {2} lines".format(self.filename, self.isSubPart, len(self.lines)))

        for raw_line in self.lines:
            parameters = []
            restOfLine = []
            line = raw_line
            while line:
                restOfLine.append(line)
                (line, result) = self.__getNextParameter(line)
                if result:
                    parameters.append(result)

            # Skip empty lines
            if not parameters:
                continue

            # Pad with empty values to simplify parsing code
            while len(parameters) < 16:
                parameters.append("")

            # Parse LDraw comments (some of which have special significance)
            if parameters[0] == "0":
                # Remove any 'NEXT' TEXMAP since we have now found a "0" line
                self.__removeIfNextTexture()

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
                        bfc.windingCCW = False
                    if "CCW" in parameters:
                        bfc.windingCCW = True
                    if "CLIP" in parameters:
                        bfc.localCull = True
                    if "NOCLIP" in parameters:
                        bfc.localCull = False
                    if "INVERTNEXT" in parameters:
                        bfc.invertNext = True
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
                    if parameters[2] == "CAMERA":
                        if Options.importCameras:
                            parameters = parameters[3:]
                            while( len(parameters) > 0):
                                if parameters[0] == "FOV":
                                    camera.vert_fov_degrees = float(parameters[1])
                                    parameters = parameters[2:]
                                elif parameters[0] == "ZNEAR":
                                    camera.near = globalScaleFactor * float(parameters[1])
                                    parameters = parameters[2:]
                                elif parameters[0] == "ZFAR":
                                    camera.far = globalScaleFactor * float(parameters[1])
                                    parameters = parameters[2:]
                                elif parameters[0] == "POSITION":
                                    camera.position = Math.scaleMatrix @ mathutils.Vector((float(parameters[1]), float(parameters[2]), float(parameters[3])))
                                    parameters = parameters[4:]
                                elif parameters[0] == "TARGET_POSITION":
                                    camera.target_position = Math.scaleMatrix @ mathutils.Vector((float(parameters[1]), float(parameters[2]), float(parameters[3])))
                                    parameters = parameters[4:]
                                elif parameters[0] == "UP_VECTOR":
                                    camera.up_vector = mathutils.Vector((float(parameters[1]), float(parameters[2]), float(parameters[3])))
                                    parameters = parameters[4:]
                                elif parameters[0] == "ORTHOGRAPHIC":
                                    camera.orthographic = True
                                    parameters = parameters[1:]
                                elif parameters[0] == "HIDDEN":
                                    camera.hidden = True
                                    parameters = parameters[1:]
                                elif parameters[0] == "NAME":
                                    camera.name = line.split(" NAME ",1)[1].strip()

                                    globalCamerasToAdd.append(camera)
                                    camera = LDrawCamera()

                                    # By definition this is the last of the parameters
                                    parameters = []
                                else:
                                    parameters = parameters[1:]
                if parameters[1] == 'STEP':
                    # Any current texture map is ended by a STEP command
                    self.__removeTextureMap()

                if parameters[1] == '!TEXMAP':
                    if parameters[2] == 'END':
                        self.__removeTextureMap(self.virtualFullFilepath)
                        self.inTexMapFallbackSection = False
                    elif parameters[2] == 'FALLBACK':
                        self.inTexMapFallbackSection = True
                    elif parameters[2] == 'START' or parameters[2] == 'NEXT':
                        if parameters[3] == 'PLANAR':
                            (x1, y1, z1, x2, y2, z2, x3, y3, z3) = map(float, parameters[4:13])
                            imageFilename = parameters[13]
                            textureMap = TextureMap(imageFilename, parameters[2], 'PLANAR', self.virtualFullFilepath, x1, y1, z1, x2, y2, z2, x3, y3, z3)
                            self.textureMaps.append(textureMap)
                        elif parameters[3] == 'CYLINDRICAL':
                            (x1, y1, z1, x2, y2, z2, x3, y3, z3, a) = map(float, parameters[4:14])
                            imageFilename = parameters[14]
                            textureMap = TextureMap(imageFilename, parameters[2], 'CYLINDRICAL', self.virtualFullFilepath, x1, y1, z1, x2, y2, z2, x3, y3, z3, a)
                            self.textureMaps.append(textureMap)
                        elif parameters[3] == 'SPHERICAL':
                            (x1, y1, z1, x2, y2, z2, x3, y3, z3, a, b) = map(float, parameters[4:15])
                            imageFilename = parameters[15]
                            textureMap = TextureMap(imageFilename, parameters[2], 'SPHERICAL', self.virtualFullFilepath, x1, y1, z1, x2, y2, z2, x3, y3, z3, a, b)
                            self.textureMaps.append(textureMap)
                if parameters[1] == '!:':
                    # Parse the textured geometry
                    bfc = self.__parseGeometryLine(line, parameters[2:], restOfLine[2:], bfc, processingLSynthParts, currentGroupNames, isGrainySlopeAllowed, parentDir)
            else:
                bfc = self.__parseGeometryLine(line, parameters, restOfLine, bfc, processingLSynthParts, currentGroupNames, isGrainySlopeAllowed, parentDir)

        #debugPrint("File {0} is part = {1}, is subPart = {2}, isModel = {3}".format(filename, self.isPart, isSubPart, self.isModel))


# **************************************************************************************
# **************************************************************************************
class BlenderMaterials:
    """Creates and stores a cache of materials for Blender"""

    __material_list = {}
    if bpy.app.version >= (4, 0, 0):
        __hasPrincipledShader = True
    else:
        __hasPrincipledShader = "ShaderNodeBsdfPrincipled" in [node.nodetype for node in getattr(bpy.types, "NODE_MT_category_SH_NEW_SHADER").category.items(None)]

    def __getGroupName(name):
        if Options.instructionsLook:
            return name + " Instructions"
        return name

    def __createNodeBasedMaterial(blenderName, col, isSlopeMaterial=False, image=None):
        """Create a node based material of whatever type is needed"""

        # Reuse current material if it exists, otherwise create a new material
        if bpy.data.materials.get(blenderName) is None:
            material = bpy.data.materials.new(blenderName)
        else:
            material = bpy.data.materials[blenderName]

        # Use nodes
        material.use_nodes = True

        if col is not None:
            # Extend an RGB colour to RGBA
            if len(col["colour"]) == 3:
                colour = col["colour"] + (1.0,)
            material.diffuse_color = getDiffuseColor(col["colour"][0:3])

        if Options.instructionsLook:
            material.blend_method = 'BLEND'
            material.show_transparent_back = False

            if col is not None:
                # Dark colours have white lines
                if LegoColours.isDark(colour):
                    material.line_color = (1.0, 1.0, 1.0, 1.0)

        nodes = material.node_tree.nodes
        links = material.node_tree.links

        # Remove any existing nodes
        for n in nodes:
            nodes.remove(n)

        if col is not None:
            isTransparent = col["alpha"] < 1.0

            if Options.instructionsLook:
                BlenderMaterials.__createCyclesBasic(nodes, links, colour, col["alpha"], "")
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
                BlenderMaterials.__createCyclesBasic(nodes, links, colour, col["alpha"], col["name"])

            if isSlopeMaterial and not Options.instructionsLook:
                BlenderMaterials.__createCyclesSlopeTexture(nodes, links, 0.6)
            elif Options.curvedWalls and not Options.instructionsLook:
                BlenderMaterials.__createCyclesConcaveWalls(nodes, links, 20 * globalScaleFactor)

            if image:
                BlenderMaterials.__createCyclesImageTextureWithAlpha(nodes, links, colour, image)

            material["Lego.isTransparent"] = isTransparent
            return material

        BlenderMaterials.__createCyclesBasic(nodes, links, (1.0, 1.0, 0.0, 1.0), 1.0, "")
        material["Lego.isTransparent"] = False
        return material

    def __nodeConcaveWalls(nodes, strength, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Concave Walls')]
        node.location = x, y
        node.inputs['Strength'].default_value = strength
        return node

    def __nodeSlopeTexture(nodes, strength, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Slope Texture')]
        node.location = x, y
        node.inputs['Strength'].default_value = strength
        return node

    def __nodeLegoStandard(nodes, colour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Standard')]
        node.location = x, y
        node.inputs['Color'].default_value = colour
        return node

    def __nodeLegoTransparentFluorescent(nodes, colour, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups[BlenderMaterials.__getGroupName('Lego Transparent Fluorescent')]
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

    def __nodeMixShader(nodes, factor, x, y):
        node = nodes.new('ShaderNodeMixShader')
        node.location = x, y
        node.inputs['Fac'].default_value = factor
        return node

    def __nodeOutput(nodes, x, y):
        node = nodes.new('ShaderNodeOutputMaterial')
        node.location = x, y
        return node

    def __nodeImageTexture(nodes, image, x, y):
        node = nodes.new('ShaderNodeTexImage')
        node.image = image
        node.interpolation = 'Closest'
        node.location = x, y
        return node

    def __nodeColorMix(nodes, x, y):
        node = nodes.new('ShaderNodeMix')
        node.data_type = 'RGBA'
        node.location = x, y
        return node

    def __nodeDielectric(nodes, roughness, reflection, transparency, ior, x, y):
        node = nodes.new('ShaderNodeGroup')
        node.node_tree = bpy.data.node_groups['PBR-Dielectric']
        node.location = x, y
        node.inputs['Roughness'].default_value = roughness
        node.inputs['Reflection'].default_value = reflection
        node.inputs['Transparency'].default_value = transparency
        node.inputs['IOR'].default_value = ior
        return node

    def __nodePrincipled(nodes, subsurface, sub_rad, metallic, roughness, clearcoat, clearcoat_roughness, ior, transmission, x, y):
        node = nodes.new('ShaderNodeBsdfPrincipled')
        node.location = x, y

        # Some inputs are renamed in Blender 4
        if bpy.app.version >= (4, 0, 0):
            node.inputs['Subsurface Weight'].default_value = subsurface
            node.inputs['Coat Weight'].default_value = clearcoat
            node.inputs['Coat Roughness'].default_value = clearcoat_roughness
            node.inputs['Transmission Weight'].default_value = transmission
        else:
            # Blender 3.X or earlier
            node.inputs['Subsurface'].default_value = subsurface
            node.inputs['Clearcoat'].default_value = clearcoat
            node.inputs['Clearcoat Roughness'].default_value = clearcoat_roughness
            node.inputs['Transmission'].default_value = transmission

        node.inputs['Subsurface Radius'].default_value = mathutils.Vector( (sub_rad, sub_rad, sub_rad) )
        node.inputs['Metallic'].default_value = metallic
        node.inputs['Roughness'].default_value = roughness
        node.inputs['IOR'].default_value = ior
        return node

    def __nodeHSV(nodes, h, s, v, x, y):
        node = nodes.new('ShaderNodeHueSaturation')
        node.location = x, y
        node.inputs[0].default_value = h
        node.inputs[1].default_value = s
        node.inputs[2].default_value = v
        return node

    def __nodeSeparateHSV(nodes, x, y):
        node = nodes.new('ShaderNodeSeparateHSV')
        node.location = x, y
        return node

    def __nodeCombineHSV(nodes, x, y):
        node = nodes.new('ShaderNodeCombineHSV')
        node.location = x, y
        return node

    def __nodeTexCoord(nodes, x, y):
        node = nodes.new('ShaderNodeTexCoord')
        node.location = x, y
        return node

    def __nodeTexWave(nodes, wave_type, wave_profile, scale, distortion, detail, detailScale, x, y):
        node = nodes.new('ShaderNodeTexWave')
        node.wave_type = wave_type
        node.wave_profile = wave_profile
        node.inputs[1].default_value = scale
        node.inputs[2].default_value = distortion
        node.inputs[3].default_value = detail
        node.inputs[4].default_value = detailScale
        node.location = x, y
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

    def __nodeAddShader(nodes, x, y):
        node = nodes.new('ShaderNodeAddShader')
        node.location = x, y
        return node

    def __nodeVolume(nodes, density, x, y):
        node = nodes.new('ShaderNodeVolumeAbsorption')
        node.inputs['Density'].default_value = density
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

    def __nodeVectorMath(nodes, operation, x, y):
        node = nodes.new('ShaderNodeVectorMath')
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

    def __nodeNoiseTexture(nodes, scale, detail, distortion, x, y):
        node = nodes.new('ShaderNodeTexNoise')
        node.location = x, y
        node.inputs['Scale'].default_value = scale
        node.inputs['Detail'].default_value = detail
        node.inputs['Distortion'].default_value = distortion
        return node

    def __nodeBumpShader(nodes, strength, distance, x, y):
        node = nodes.new('ShaderNodeBump')
        node.location = x, y
        node.inputs[0].default_value = strength
        node.inputs[1].default_value = distance
        return node

    def __nodeRefraction(nodes, roughness, ior, x, y):
        node = nodes.new('ShaderNodeBsdfRefraction')
        node.inputs['Roughness'].default_value = roughness
        node.inputs['IOR'].default_value = ior
        node.location = x, y
        return node

    def __getGroup(nodes):
        out = None
        for x in nodes:
            if x.type == 'GROUP':
                return x
        return None

    def __createCyclesImageTextureWithAlpha(nodes, links, colour, image):
        """Image texture for Cycles render engine"""
        imageTextureNode = BlenderMaterials.__nodeImageTexture(nodes, image, -500, 50)
        colourMixNode = BlenderMaterials.__nodeColorMix(nodes, -200, 250)
        colourMixNode.inputs['A'].default_value = colour
        out = BlenderMaterials.__getGroup(nodes)

        links.new(imageTextureNode.outputs['Color'], colourMixNode.inputs['B'])
        links.new(imageTextureNode.outputs['Alpha'], colourMixNode.inputs['Factor'])
        links.new(colourMixNode.outputs['Result'], out.inputs['Color'])

    def __createCyclesConcaveWalls(nodes, links, strength):
        """Concave wall normals for Cycles render engine"""
        node = BlenderMaterials.__nodeConcaveWalls(nodes, strength, -200, 5)
        out = BlenderMaterials.__getGroup(nodes)
        if out is not None:
            links.new(node.outputs['Normal'], out.inputs['Normal'])

    def __createCyclesSlopeTexture(nodes, links, strength):
        """Slope face normals for Cycles render engine"""
        node = BlenderMaterials.__nodeSlopeTexture(nodes, strength, -200, 5)
        out = BlenderMaterials.__getGroup(nodes)
        if out is not None:
            links.new(node.outputs['Normal'], out.inputs['Normal'])

    def __createCyclesBasic(nodes, links, diffColour, alpha, colName):
        """Basic Material for Cycles render engine."""

        if alpha < 1:
            if LegoColours.isFluorescentTransparent(colName):
                node = BlenderMaterials.__nodeLegoTransparentFluorescent(nodes, diffColour, 0, 5)
            else:
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
            printWarningOnce("Could not decode {0} to a colour".format(colourName))
            return None
        return {
            "name":         colourName,
            "colour":       linearRGBA[0:3],
            "alpha":        linearRGBA[3],
            "luminance":    0.0,
            "material":     "BASIC"
        }

    # **********************************************************************************
    def __tryLoadImage(filepath):
        try:
            image = bpy.data.images.load(filepath)
        except RuntimeError as e:
            image = None
        return image

    # **********************************************************************************
    def getMaterial(colourName, isSlopeMaterial, imageFilename, parentDir):
        postfix = colourName
        if isSlopeMaterial:
            postfix = colourName + "_s"

        if not Options.instructionsLook and Options.curvedWalls and not isSlopeMaterial:
            postfix += "_c"

        if imageFilename:
            postfix += "_" + imageFilename.lower()

        # Create a name for the material based on the colour and texture image
        if Options.instructionsLook:
            blenderName = "MatInst_{0}".format(postfix)
        else:
            blenderName = "Material_{0}".format(postfix)

        # If it's already in the cache, use that
        if (blenderName in BlenderMaterials.__material_list):
            result = BlenderMaterials.__material_list[blenderName]
            return result

        # If the name already exists in Blender, use that
        if Options.overwriteExistingMaterials is False:
            if blenderName in bpy.data.materials:
                return bpy.data.materials[blenderName]

        image = None
        if imageFilename:
            # Load the image
            image = CachedFiles.get(imageFilename)
            if not image:
                # Create full filepath with case sensitivity fixed, with "textures/" prefix
                fullFilepath = FileSystem.locate(os.path.join("textures", imageFilename), parentDir)
                image = BlenderMaterials.__tryLoadImage(fullFilepath)

                if not image:
                    fullFilepath = FileSystem.locate(imageFilename, parentDir)
                    image = BlenderMaterials.__tryLoadImage(fullFilepath)

                CachedFiles.add(imageFilename, image)

        # Create new material
        col = BlenderMaterials.__getColourData(colourName)
        material = BlenderMaterials.__createNodeBasedMaterial(blenderName, col, isSlopeMaterial, image)

        if material is None:
            printWarningOnce("Could not create material for blenderName {0}".format(blenderName))

        # Add material to cache
        BlenderMaterials.__material_list[blenderName] = material
        return material

    # **********************************************************************************
    def clearCache():
        BlenderMaterials.__material_list = {}

    # **********************************************************************************
    def addInputSocket(group, my_socket_type, myname):
        if bpy.app.version >= (4, 0, 0):
            if my_socket_type.endswith("FloatFactor"):
                my_socket_type = my_socket_type[:-6]
            elif my_socket_type.endswith("VectorDirection"):
                my_socket_type = my_socket_type[:-9]
            group.interface.new_socket(name=myname, in_out="INPUT", socket_type=my_socket_type)
        else:
            if my_socket_type.endswith("Vector"):
                my_socket_type += "Direction"
            group.inputs.new(my_socket_type, myname)

    # **********************************************************************************
    def addOutputSocket(group, my_socket_type, myname):
        if bpy.app.version >= (4, 0, 0):
            if my_socket_type.endswith("FloatFactor"):
                my_socket_type = my_socket_type[:-6]
            elif my_socket_type.endswith("VectorDirection"):
                my_socket_type = my_socket_type[:-9]
            group.interface.new_socket(name=myname, in_out="OUTPUT", socket_type=my_socket_type)
        else:
            if my_socket_type.endswith("Vector"):
                my_socket_type += "Direction"
            group.outputs.new(my_socket_type, myname)

    # **********************************************************************************
    def setDefaults(group, name, default_value, min_value, max_value):
        if bpy.app.version >= (4, 0, 0):
            group_inputs = group.nodes["Group Input"].outputs
            group_inputs[name].default_value = default_value
            # TODO: How to set min_value and max_value?
        else:
            group_inputs = group.inputs
            group_inputs[name].default_value = default_value
            group_inputs[name].min_value = min_value
            group_inputs[name].max_value = max_value

    # **********************************************************************************
    def __createGroup(name, x1, y1, x2, y2, createShaderOutput):
        group = bpy.data.node_groups.new(name, 'ShaderNodeTree')

        # create input node
        node_input = group.nodes.new('NodeGroupInput')
        node_input.location = (x1,y1)

        # create output node
        node_output = group.nodes.new('NodeGroupOutput')
        node_output.location = (x2,y2)
        if createShaderOutput:
            BlenderMaterials.addOutputSocket(group, 'NodeSocketShader', 'Shader')
        return (group, node_input, node_output)

    # **********************************************************************************
    def __createBlenderDistanceToCenterNodeGroup():
        if bpy.data.node_groups.get('Distance-To-Center') is None:
            debugPrint("createBlenderDistanceToCenterNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('Distance-To-Center', -930, 0, 240, 0, False)
            BlenderMaterials.addOutputSocket(group, 'NodeSocketVectorDirection', 'Vector')

            # create nodes
            node_texture_coordinate = BlenderMaterials.__nodeTexCoord(group.nodes, -730, 0)

            node_vector_subtraction1 = BlenderMaterials.__nodeVectorMath(group.nodes, 'SUBTRACT', -535, 0)
            node_vector_subtraction1.inputs[1].default_value[0] = 0.5
            node_vector_subtraction1.inputs[1].default_value[1] = 0.5
            node_vector_subtraction1.inputs[1].default_value[2] = 0.5

            node_normalize = BlenderMaterials.__nodeVectorMath(group.nodes, 'NORMALIZE', -535, -245)
            node_dot_product = BlenderMaterials.__nodeVectorMath(group.nodes, 'DOT_PRODUCT', -340, -125)

            node_multiply = group.nodes.new('ShaderNodeMixRGB')
            node_multiply.blend_type = 'MULTIPLY'
            node_multiply.inputs['Fac'].default_value = 1.0
            node_multiply.location = -145, -125

            node_vector_subtraction2 = BlenderMaterials.__nodeVectorMath(group.nodes, 'SUBTRACT', 40, 0)

            # link nodes together
            group.links.new(node_texture_coordinate.outputs['Generated'], node_vector_subtraction1.inputs[0])
            group.links.new(node_texture_coordinate.outputs['Normal'], node_normalize.inputs[0])
            group.links.new(node_vector_subtraction1.outputs['Vector'], node_dot_product.inputs[0])
            group.links.new(node_normalize.outputs['Vector'], node_dot_product.inputs[1])
            group.links.new(node_dot_product.outputs['Value'], node_multiply.inputs['Color1'])
            group.links.new(node_normalize.outputs['Vector'], node_multiply.inputs['Color2'])
            group.links.new(node_vector_subtraction1.outputs['Vector'], node_vector_subtraction2.inputs[0])
            group.links.new(node_multiply.outputs['Color'], node_vector_subtraction2.inputs[1])
            group.links.new(node_vector_subtraction2.outputs['Vector'], node_output.inputs[0])

    # **********************************************************************************
    def __createBlenderVectorElementPowerNodeGroup():
        if bpy.data.node_groups.get('Vector-Element-Power') is None:
            debugPrint("createBlenderVectorElementPowerNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('Vector-Element-Power', -580, 0, 400, 0, False)
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloat', 'Exponent')
            BlenderMaterials.addInputSocket(group, 'NodeSocketVectorDirection', 'Vector')
            BlenderMaterials.addOutputSocket(group, 'NodeSocketVectorDirection', 'Vector')

            # create nodes
            node_separate_xyz = group.nodes.new('ShaderNodeSeparateXYZ')
            node_separate_xyz.location = -385, -140

            node_abs_x = BlenderMaterials.__nodeMath(group.nodes, 'ABSOLUTE', -180, 180)
            node_abs_y = BlenderMaterials.__nodeMath(group.nodes, 'ABSOLUTE', -180, 0)
            node_abs_z = BlenderMaterials.__nodeMath(group.nodes, 'ABSOLUTE', -180, -180)

            node_power_x = BlenderMaterials.__nodeMath(group.nodes, 'POWER', 20, 180)
            node_power_y = BlenderMaterials.__nodeMath(group.nodes, 'POWER', 20, 0)
            node_power_z = BlenderMaterials.__nodeMath(group.nodes, 'POWER', 20, -180)

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

    # **********************************************************************************
    def __createBlenderConvertToNormalsNodeGroup():
        if bpy.data.node_groups.get('Convert-To-Normals') is None:
            debugPrint("createBlenderConvertToNormalsNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('Convert-To-Normals', -490, 0, 400, 0, False)
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloat', 'Vector Length')
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloat', 'Smoothing')
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloat', 'Strength')
            BlenderMaterials.addInputSocket(group, 'NodeSocketVectorDirection', 'Normal')
            BlenderMaterials.addOutputSocket(group, 'NodeSocketVectorDirection', 'Normal')

            # create nodes
            node_power = BlenderMaterials.__nodeMath(group.nodes, 'POWER', -290, 150)

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

    # **********************************************************************************
    def __createBlenderConcaveWallsNodeGroup():
        if bpy.data.node_groups.get('Concave Walls') is None:
            debugPrint("createBlenderConcaveWallsNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('Concave Walls', -530, 0, 300, 0, False)
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloat', 'Strength')
            BlenderMaterials.addInputSocket(group, 'NodeSocketVectorDirection', 'Normal')
            BlenderMaterials.addOutputSocket(group, 'NodeSocketVectorDirection', 'Normal')

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

    # **********************************************************************************
    def __createBlenderSlopeTextureNodeGroup():
        global globalScaleFactor

        if bpy.data.node_groups.get('Slope Texture') is None:
            debugPrint("createBlenderSlopeTextureNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('Slope Texture', -530, 0, 300, 0, False)
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloat', 'Strength')
            BlenderMaterials.addInputSocket(group, 'NodeSocketVectorDirection', 'Normal')
            BlenderMaterials.addOutputSocket(group, 'NodeSocketVectorDirection', 'Normal')

            # create nodes
            node_texture_coordinate = BlenderMaterials.__nodeTexCoord(group.nodes, -300, 240)
            node_voronoi = BlenderMaterials.__nodeVoronoi(group.nodes, 3.0/globalScaleFactor, -100, 155)
            node_bump = BlenderMaterials.__nodeBumpShader(group.nodes, 0.3, 0.08, 90, 50)
            node_bump.invert = True

            # link nodes together
            group.links.new(node_texture_coordinate.outputs['Object'], node_voronoi.inputs['Vector'])
            group.links.new(node_voronoi.outputs['Distance'], node_bump.inputs['Height'])
            group.links.new(node_input.outputs['Strength'], node_bump.inputs['Strength'])
            group.links.new(node_input.outputs['Normal'], node_bump.inputs['Normal'])
            group.links.new(node_bump.outputs['Normal'], node_output.inputs['Normal'])

    # **********************************************************************************
    def __createBlenderFresnelNodeGroup():
        if bpy.data.node_groups.get('PBR-Fresnel-Roughness') is None:
            debugPrint("createBlenderFresnelNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('PBR-Fresnel-Roughness', -530, 0, 300, 0, False)
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloatFactor', 'Roughness')
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloat', 'IOR')
            BlenderMaterials.addInputSocket(group, 'NodeSocketVectorDirection', 'Normal')
            BlenderMaterials.addOutputSocket(group, 'NodeSocketFloatFactor', 'Fresnel Factor')

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

    # **********************************************************************************
    def __createBlenderReflectionNodeGroup():
        if bpy.data.node_groups.get('PBR-Reflection') is None:
            debugPrint("createBlenderReflectionNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('PBR-Reflection', -530, 0, 300, 0, True)
            BlenderMaterials.addInputSocket(group, 'NodeSocketShader', 'Shader')
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloatFactor', 'Roughness')
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloatFactor', 'Reflection')
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloat', 'IOR')
            BlenderMaterials.addInputSocket(group, 'NodeSocketVectorDirection', 'Normal')

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

    # **********************************************************************************
    def __createBlenderDielectricNodeGroup():
        if bpy.data.node_groups.get('PBR-Dielectric') is None:
            debugPrint("createBlenderDielectricNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('PBR-Dielectric', -530, 70, 500, 0, True)
            BlenderMaterials.addInputSocket(group, 'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloatFactor','Roughness')
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloatFactor','Reflection')
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloatFactor','Transparency')
            BlenderMaterials.addInputSocket(group, 'NodeSocketFloat','IOR')
            BlenderMaterials.addInputSocket(group, 'NodeSocketVectorDirection','Normal')

            BlenderMaterials.setDefaults(group, 'IOR',          1.46, 0.0, 100.0)
            BlenderMaterials.setDefaults(group, 'Roughness',    0.2,  0.0,   1.0)
            BlenderMaterials.setDefaults(group, 'Reflection',   0.1,  0.0,   1.0)
            BlenderMaterials.setDefaults(group, 'Transparency', 0.0,  0.0,   1.0)

            node_diffuse = group.nodes.new('ShaderNodeBsdfDiffuse')
            node_diffuse.location = (-110,145)

            node_reflection = group.nodes.new('ShaderNodeGroup')
            node_reflection.node_tree = bpy.data.node_groups['PBR-Reflection']
            node_reflection.location = (100,115)

            node_power = BlenderMaterials.__nodeMath(group.nodes, 'POWER', -330, -105)
            node_power.inputs[1].default_value = 2.0

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

    # **********************************************************************************
    def __getSubsurfaceColor(node):
        if 'Subsurface Color' in node.inputs:
            # Blender 3
            return node.inputs['Subsurface Color']

        # Blender 4 - Subsurface Colour has been removed, so just use the base colour instead
        return node.inputs['Base Color']

    # **********************************************************************************
    def __createBlenderLegoStandardNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Standard')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoStandardNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -250, 0, 300, 0, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if Options.instructionsLook:
                # TODO: What about Alpha?
                node_emission = BlenderMaterials.__nodeEmission(group.nodes, 0, 0)
                group.links.new(node_input.outputs['Color'],       node_emission.inputs['Color'])
                group.links.new(node_emission.outputs['Emission'], node_output.inputs['Shader'])
            else:
                if BlenderMaterials.usePrincipledShader:
                    node_main = BlenderMaterials.__nodePrincipled(group.nodes, 5 * globalScaleFactor, 0.05, 0.0, 0.1, 0.0, 0.0, 1.45, 0.0, 0, 0)
                    output_name = 'BSDF'
                    color_name = 'Base Color'
                    group.links.new(node_input.outputs['Color'], BlenderMaterials.__getSubsurfaceColor(node_main))
                else:
                    node_main = BlenderMaterials.__nodeDielectric(group.nodes, 0.2, 0.1, 0.0, 1.46, 0, 0)
                    output_name = 'Shader'
                    color_name = 'Color'

                # link nodes together
                group.links.new(node_input.outputs['Color'],        node_main.inputs[color_name])
                group.links.new(node_input.outputs['Normal'],       node_main.inputs['Normal'])
                group.links.new(node_main.outputs[output_name],     node_output.inputs['Shader'])


    # **********************************************************************************
    def __createBlenderLegoTransparentNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Transparent')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoTransparentNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -250, 0, 300, 0, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if Options.instructionsLook:
                node_emission    = BlenderMaterials.__nodeEmission(group.nodes, 0, 0)
                node_transparent = BlenderMaterials.__nodeTransparent(group.nodes, 0, 100)
                node_mix1        = BlenderMaterials.__nodeMixShader(group.nodes, 0.5, 400, 100)
                node_light       = BlenderMaterials.__nodeLightPath(group.nodes, 200, 400)
                node_less        = BlenderMaterials.__nodeMath(group.nodes, 'LESS_THAN', 400, 400)
                node_mix2        = BlenderMaterials.__nodeMixShader(group.nodes, 0.5, 600, 300)

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
                if BlenderMaterials.usePrincipledShader:
                    node_principled  = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 0.0, 0.05, 0.0, 0.0, 1.585, 1.0, 45, 340)

                    # link nodes together
                    group.links.new(node_input.outputs['Color'],       node_principled.inputs['Base Color'])
                    group.links.new(node_input.outputs['Normal'],      node_principled.inputs['Normal'])
                    group.links.new(node_principled.outputs['BSDF'],   node_output.inputs['Shader'])
                else:
                    node_main = BlenderMaterials.__nodeDielectric(group.nodes, 0.15, 0.1, 0.97, 1.46, 0, 0)

                    # link nodes together
                    group.links.new(node_input.outputs['Color'],       node_main.inputs['Color'])
                    group.links.new(node_input.outputs['Normal'],      node_main.inputs['Normal'])
                    group.links.new(node_main.outputs['Shader'],       node_output.inputs['Shader'])


    # **********************************************************************************
    def __createBlenderLegoTransparentFluorescentNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Transparent Fluorescent')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoTransparentFluorescentNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -250, 0, 300, 0, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if Options.instructionsLook:
                node_emission    = BlenderMaterials.__nodeEmission(group.nodes, 0, 0)
                node_transparent = BlenderMaterials.__nodeTransparent(group.nodes, 0, 100)
                node_mix1        = BlenderMaterials.__nodeMixShader(group.nodes, 0.5, 400, 100)
                node_light       = BlenderMaterials.__nodeLightPath(group.nodes, 200, 400)
                node_less        = BlenderMaterials.__nodeMath(group.nodes, 'LESS_THAN', 400, 400)
                node_mix2        = BlenderMaterials.__nodeMixShader(group.nodes, 0.5, 600, 300)

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
                if BlenderMaterials.usePrincipledShader:
                    node_principled  = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 0.0, 0.05, 0.0, 0.0, 1.585, 1.0, 45, 340)
                    node_emission    = BlenderMaterials.__nodeEmission(group.nodes, 45, -160)
                    node_mix         = BlenderMaterials.__nodeMixShader(group.nodes, 0.03, 300, 290)

                    node_output.location = 500, 290

                    # link nodes together
                    group.links.new(node_input.outputs['Color'],       node_principled.inputs['Base Color'])
                    group.links.new(node_input.outputs['Color'],       node_emission.inputs['Color'])
                    group.links.new(node_input.outputs['Normal'],      node_principled.inputs['Normal'])
                    group.links.new(node_principled.outputs['BSDF'],   node_mix.inputs[1])
                    group.links.new(node_emission.outputs['Emission'], node_mix.inputs[2])
                    group.links.new(node_mix.outputs[0],               node_output.inputs['Shader'])

                else:
                    node_main = BlenderMaterials.__nodeDielectric(group.nodes, 0.15, 0.1, 0.97, 1.46, 0, 0)

                    # link nodes together
                    group.links.new(node_input.outputs['Color'],       node_main.inputs['Color'])
                    group.links.new(node_input.outputs['Normal'],      node_main.inputs['Normal'])
                    group.links.new(node_main.outputs['Shader'],       node_output.inputs['Shader'])


    # **********************************************************************************
    def __createBlenderLegoRubberNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Rubber Solid')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoRubberNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, 45-950, 340-50, 45+200, 340-5, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_noise = BlenderMaterials.__nodeNoiseTexture(group.nodes, 250, 2, 0.0, 45-770, 340-200)
                node_bump1 = BlenderMaterials.__nodeBumpShader(group.nodes, 1.0, 0.3, 45-366, 340-200)
                node_bump2 = BlenderMaterials.__nodeBumpShader(group.nodes, 1.0, 0.1, 45-184, 340-115)
                node_subtract = BlenderMaterials.__nodeMath(group.nodes, 'SUBTRACT', 45-570, 340-216)
                node_principled  = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 0.0, 0.4, 0.03, 0.0, 1.45, 0.0, 45, 340)

                node_subtract.inputs[1].default_value = 0.4

                group.links.new(node_input.outputs['Color'],       node_principled.inputs['Base Color'])
                group.links.new(node_principled.outputs['BSDF'],   node_output.inputs[0])
                group.links.new(node_noise.outputs['Color'],       node_subtract.inputs[0])
                group.links.new(node_subtract.outputs[0],          node_bump1.inputs['Height'])
                group.links.new(node_bump1.outputs['Normal'],      node_bump2.inputs['Normal'])
                group.links.new(node_bump2.outputs['Normal'],      node_principled.inputs['Normal'])
            else:
                node_dielectric = BlenderMaterials.__nodeDielectric(group.nodes, 0.5, 0.07, 0.0, 1.52, 0, 0)

                # link nodes together
                group.links.new(node_input.outputs['Color'],       node_dielectric.inputs['Color'])
                group.links.new(node_input.outputs['Normal'],      node_dielectric.inputs['Normal'])
                group.links.new(node_dielectric.outputs['Shader'], node_output.inputs['Shader'])


    # **********************************************************************************
    def __createBlenderLegoRubberTranslucentNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Rubber Translucent')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoRubberTranslucentNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -250, 0, 250, 0, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_noise = BlenderMaterials.__nodeNoiseTexture(group.nodes, 250, 2, 0.0, 45-770, 340-200)
                node_bump1 = BlenderMaterials.__nodeBumpShader(group.nodes, 1.0, 0.3, 45-366, 340-200)
                node_bump2 = BlenderMaterials.__nodeBumpShader(group.nodes, 1.0, 0.1, 45-184, 340-115)
                node_subtract = BlenderMaterials.__nodeMath(group.nodes, 'SUBTRACT', 45-570, 340-216)
                node_principled  = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 0.0, 0.4, 0.03, 0.0, 1.45, 0.0, 45, 340)
                node_mix = BlenderMaterials.__nodeMixShader(group.nodes, 0.8, 300, 290)
                node_refraction = BlenderMaterials.__nodeRefraction(group.nodes, 0.0, 1.45, 290-242, 154-330)
                node_input.location = -320, 290
                node_output.location = 530, 285

                node_subtract.inputs[1].default_value = 0.4

                group.links.new(node_input.outputs['Normal'],      node_refraction.inputs['Normal'])
                group.links.new(node_refraction.outputs[0],        node_mix.inputs[2])
                group.links.new(node_principled.outputs[0],        node_mix.inputs[1])
                group.links.new(node_mix.outputs[0],               node_output.inputs[0])
                group.links.new(node_input.outputs['Color'],       node_principled.inputs['Base Color'])
                group.links.new(node_noise.outputs['Color'],       node_subtract.inputs[0])
                group.links.new(node_subtract.outputs[0],          node_bump1.inputs['Height'])
                group.links.new(node_bump1.outputs['Normal'],      node_bump2.inputs['Normal'])
                group.links.new(node_bump2.outputs['Normal'],      node_principled.inputs['Normal'])
                group.links.new(node_mix.outputs[0],               node_output.inputs[0])
            else:
                node_dielectric = BlenderMaterials.__nodeDielectric(group.nodes, 0.15, 0.1, 0.97, 1.46, 0, 0)

                # link nodes together
                group.links.new(node_input.outputs['Color'],       node_dielectric.inputs['Color'])
                group.links.new(node_input.outputs['Normal'],      node_dielectric.inputs['Normal'])
                group.links.new(node_dielectric.outputs['Shader'], node_output.inputs['Shader'])

    # **************************************************************************************
    def __createBlenderLegoEmissionNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Emission')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoEmissionNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 90, 250, 0, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketFloatFactor','Luminance')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            node_emit  = BlenderMaterials.__nodeEmission(group.nodes, -242, -123)
            node_mix   = BlenderMaterials.__nodeMixShader(group.nodes, 0.5, 0, 90)

            if BlenderMaterials.usePrincipledShader:
                node_main = BlenderMaterials.__nodePrincipled(group.nodes, 1.0, 0.05, 0.0, 0.5, 0.0, 0.03, 1.45, 0.0, -242, 154+240)
                group.links.new(node_input.outputs['Color'],     BlenderMaterials.__getSubsurfaceColor(node_main))
                group.links.new(node_input.outputs['Color'],     node_emit.inputs['Color'])
                main_colour = 'Base Color'
            else:
                node_main = BlenderMaterials.__nodeTranslucent(group.nodes, -242, 154)
                main_colour = 'Color'

            # link nodes together
            group.links.new(node_input.outputs['Color'],     node_main.inputs[main_colour])
            group.links.new(node_input.outputs['Normal'],    node_main.inputs['Normal'])
            group.links.new(node_input.outputs['Luminance'], node_mix.inputs[0])
            group.links.new(node_main.outputs[0],            node_mix.inputs[1])
            group.links.new(node_emit.outputs[0],            node_mix.inputs[2])
            group.links.new(node_mix.outputs[0],             node_output.inputs[0])

    # **********************************************************************************
    def __createBlenderLegoChromeNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Chrome')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoChromeNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 90, 250, 0, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_hsv         = BlenderMaterials.__nodeHSV(group.nodes, 0.5, 0.9, 2.0, -90, 0)
                node_principled  = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 1.0, 0.0, 1.0, 0.0, 2.4, 0.0, 100, 0)

                node_output.location = (575, -140)

                # link nodes together
                group.links.new(node_input.outputs['Color'],       node_hsv.inputs['Color'])
                group.links.new(node_input.outputs['Normal'],      node_principled.inputs['Normal'])
                group.links.new(node_hsv.outputs['Color'],         node_principled.inputs['Base Color'])
                group.links.new(node_principled.outputs['BSDF'],   node_output.inputs[0])
            else:
                node_glossyOne = BlenderMaterials.__nodeGlossy(group.nodes, (1,1,1,1), 0.03, 'GGX', -242, 154)
                node_glossyTwo = BlenderMaterials.__nodeGlossy(group.nodes, (1.0, 1.0, 1.0, 1.0), 0.03, 'BECKMANN', -242, -23)
                node_mix       = BlenderMaterials.__nodeMixShader(group.nodes, 0.01, 0, 90)

                # link nodes together
                group.links.new(node_input.outputs['Color'],  node_glossyOne.inputs['Color'])
                group.links.new(node_input.outputs['Normal'], node_glossyOne.inputs['Normal'])
                group.links.new(node_input.outputs['Normal'], node_glossyTwo.inputs['Normal'])
                group.links.new(node_glossyOne.outputs[0],    node_mix.inputs[1])
                group.links.new(node_glossyTwo.outputs[0],    node_mix.inputs[2])
                group.links.new(node_mix.outputs[0],          node_output.inputs[0])

    # **********************************************************************************
    def __createBlenderLegoPearlescentNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Pearlescent')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoPearlescentNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 90, 630, 95, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_principled  = BlenderMaterials.__nodePrincipled(group.nodes, 1.0, 0.25, 0.5, 0.2, 1.0, 0.2, 1.6, 0.0, 310, 95)
                node_sep_hsv     = BlenderMaterials.__nodeSeparateHSV(group.nodes, -240, 75)
                node_multiply    = BlenderMaterials.__nodeMath(group.nodes, 'MULTIPLY', -60, 0)
                node_com_hsv     = BlenderMaterials.__nodeCombineHSV(group.nodes, 110, 95)
                node_tex_coord   = BlenderMaterials.__nodeTexCoord(group.nodes, -730, -223)
                node_tex_wave    = BlenderMaterials.__nodeTexWave(group.nodes, 'BANDS', 'SIN', 0.5, 40, 1, 1.5, -520, -190)
                node_color_ramp  = BlenderMaterials.__nodeColorRamp(group.nodes, 0.329, (0.89, 0.89, 0.89, 1), 0.820, (1, 1, 1, 1), -340, -70)
                element = node_color_ramp.color_ramp.elements.new(1.0)
                element.color = (1.118, 1.118, 1.118, 1)

                # link nodes together
                group.links.new(node_input.outputs['Color'], node_sep_hsv.inputs['Color'])
                group.links.new(node_input.outputs['Normal'], node_principled.inputs['Normal'])
                group.links.new(node_sep_hsv.outputs['H'], node_com_hsv.inputs['H'])
                group.links.new(node_sep_hsv.outputs['S'], node_com_hsv.inputs['S'])
                group.links.new(node_sep_hsv.outputs['V'], node_multiply.inputs[0])
                group.links.new(node_com_hsv.outputs['Color'], node_principled.inputs['Base Color'])
                group.links.new(node_com_hsv.outputs['Color'], BlenderMaterials.__getSubsurfaceColor(node_principled))
                group.links.new(node_tex_coord.outputs['Object'], node_tex_wave.inputs['Vector'])
                group.links.new(node_tex_wave.outputs['Fac'], node_color_ramp.inputs['Fac'])
                group.links.new(node_color_ramp.outputs['Color'], node_multiply.inputs[1])
                group.links.new(node_multiply.outputs[0], node_com_hsv.inputs['V'])
                group.links.new(node_principled.outputs['BSDF'], node_output.inputs[0])
            else:
                node_diffuse = BlenderMaterials.__nodeDiffuse(group.nodes, 0.0, -242, -23)
                node_glossy  = BlenderMaterials.__nodeGlossy(group.nodes, (1,1,1,1), 0.05, 'BECKMANN', -242, 154)
                node_mix     = BlenderMaterials.__nodeMixShader(group.nodes, 0.4, 0, 90)

                # link nodes together
                group.links.new(node_input.outputs['Color'],  node_diffuse.inputs['Color'])
                group.links.new(node_input.outputs['Color'],  node_glossy.inputs['Color'])
                group.links.new(node_input.outputs['Normal'], node_diffuse.inputs['Normal'])
                group.links.new(node_input.outputs['Normal'], node_glossy.inputs['Normal'])
                group.links.new(node_glossy.outputs[0],   node_mix.inputs[1])
                group.links.new(node_diffuse.outputs[0],  node_mix.inputs[2])
                group.links.new(node_mix.outputs[0],      node_output.inputs[0])

    # **********************************************************************************
    def __createBlenderLegoMetalNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Metal')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoMetalNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 90, 250, 0, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_principled  = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 0.8, 0.2, 0.0, 0.03, 1.45, 0.0, 310, 95)

                group.links.new(node_input.outputs['Color'], node_principled.inputs['Base Color'])
                group.links.new(node_input.outputs['Normal'], node_principled.inputs['Normal'])
                group.links.new(node_principled.outputs[0], node_output.inputs['Shader'])
            else:
                node_dielectric = BlenderMaterials.__nodeDielectric(group.nodes, 0.05, 0.2, 0.0, 1.46, -242, 0)
                node_glossy = BlenderMaterials.__nodeGlossy(group.nodes, (1,1,1,1), 0.2, 'BECKMANN', -242, 154)
                node_mix = BlenderMaterials.__nodeMixShader(group.nodes, 0.4, 0, 90)

                # link nodes together
                group.links.new(node_input.outputs['Color'], node_glossy.inputs['Color'])
                group.links.new(node_input.outputs['Color'], node_dielectric.inputs['Color'])
                group.links.new(node_input.outputs['Normal'], node_glossy.inputs['Normal'])
                group.links.new(node_input.outputs['Normal'], node_dielectric.inputs['Normal'])
                group.links.new(node_glossy.outputs[0],     node_mix.inputs[1])
                group.links.new(node_dielectric.outputs[0], node_mix.inputs[2])
                group.links.new(node_mix.outputs[0],        node_output.inputs[0])

    # **********************************************************************************
    def __createBlenderLegoGlitterNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Glitter')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoGlitterNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 0, 410, 0, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Glitter Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_voronoi     = BlenderMaterials.__nodeVoronoi(group.nodes, 100, -222, 310)
                node_gamma       = BlenderMaterials.__nodeGamma(group.nodes, 50, 0, 200)
                node_mix         = BlenderMaterials.__nodeMixShader(group.nodes, 0.05, 210, 90+25)
                node_principled1 = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 0.0, 0.2, 0.0, 0.03, 1.585, 1.0, 45-270, 340-210)
                node_principled2 = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 0.0, 0.5, 0.0, 0.03, 1.45, 0.0, 45-270, 340-750)

                group.links.new(node_input.outputs['Color'], node_principled1.inputs['Base Color'])
                group.links.new(node_input.outputs['Glitter Color'], node_principled2.inputs['Base Color'])
                group.links.new(node_input.outputs['Normal'], node_principled1.inputs['Normal'])
                group.links.new(node_input.outputs['Normal'], node_principled2.inputs['Normal'])
                group.links.new(node_voronoi.outputs['Color'], node_gamma.inputs['Color'])
                group.links.new(node_gamma.outputs[0], node_mix.inputs[0])
                group.links.new(node_principled1.outputs['BSDF'], node_mix.inputs[1])
                group.links.new(node_principled2.outputs['BSDF'], node_mix.inputs[2])
                group.links.new(node_mix.outputs[0], node_output.inputs[0])
            else:
                node_glass   = BlenderMaterials.__nodeGlass(group.nodes, 0.05, 1.46, 'BECKMANN', -242, 154)
                node_glossy  = BlenderMaterials.__nodeGlossy(group.nodes, (1,1,1,1), 0.05, 'BECKMANN', -242, -23)
                node_diffuse = BlenderMaterials.__nodeDiffuse(group.nodes, 0.0, -12, -49)
                node_voronoi = BlenderMaterials.__nodeVoronoi(group.nodes, 100, -232, 310)
                node_gamma   = BlenderMaterials.__nodeGamma(group.nodes, 50, 0, 200)
                node_mixOne  = BlenderMaterials.__nodeMixShader(group.nodes, 0.05, 0, 90)
                node_mixTwo  = BlenderMaterials.__nodeMixShader(group.nodes, 0.5, 200, 90)

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

    # **********************************************************************************
    def __createBlenderLegoSpeckleNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Speckle')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoSpeckleNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 0, 410, 0, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Speckle Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_voronoi     = BlenderMaterials.__nodeVoronoi(group.nodes, 50, -222, 310)
                node_gamma       = BlenderMaterials.__nodeGamma(group.nodes, 3.5, 0, 200)
                node_mix         = BlenderMaterials.__nodeMixShader(group.nodes, 0.05, 210, 90+25)
                node_principled1 = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 0.0, 0.1, 0.0, 0.03, 1.45, 0.0, 45-270, 340-210)
                node_principled2 = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 1.0, 0.5, 0.0, 0.03, 1.45, 0.0, 45-270, 340-750)

                group.links.new(node_input.outputs['Color'], node_principled1.inputs['Base Color'])
                group.links.new(node_input.outputs['Speckle Color'], node_principled2.inputs['Base Color'])
                group.links.new(node_input.outputs['Normal'], node_principled1.inputs['Normal'])
                group.links.new(node_input.outputs['Normal'], node_principled2.inputs['Normal'])
                group.links.new(node_voronoi.outputs['Color'], node_gamma.inputs['Color'])
                group.links.new(node_gamma.outputs[0], node_mix.inputs[0])
                group.links.new(node_principled1.outputs['BSDF'], node_mix.inputs[1])
                group.links.new(node_principled2.outputs['BSDF'], node_mix.inputs[2])
                group.links.new(node_mix.outputs[0], node_output.inputs[0])
            else:
                node_diffuseOne = BlenderMaterials.__nodeDiffuse(group.nodes, 0.0, -242, 131)
                node_glossy     = BlenderMaterials.__nodeGlossy(group.nodes, (0.333, 0.333, 0.333, 1.0), 0.2, 'BECKMANN', -242, -23)
                node_diffuseTwo = BlenderMaterials.__nodeDiffuse(group.nodes, 0.0, -12, -49)
                node_voronoi    = BlenderMaterials.__nodeVoronoi(group.nodes, 100, -232, 310)
                node_gamma      = BlenderMaterials.__nodeGamma(group.nodes, 20, 0, 200)
                node_mixOne     = BlenderMaterials.__nodeMixShader(group.nodes, 0.2, 0, 90)
                node_mixTwo     = BlenderMaterials.__nodeMixShader(group.nodes, 0.5, 200, 90)

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

    # **********************************************************************************
    def __createBlenderLegoMilkyWhiteNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Milky White')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoMilkyWhiteNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 0, 350, 0, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_principled = BlenderMaterials.__nodePrincipled(group.nodes, 1.0, 0.05, 0.0, 0.5, 0.0, 0.03, 1.45, 0.0, 45-270, 340-210)
                node_translucent = BlenderMaterials.__nodeTranslucent(group.nodes, -225, -382)
                node_mix = BlenderMaterials.__nodeMixShader(group.nodes, 0.5, 65, -40)

                group.links.new(node_input.outputs['Color'], node_principled.inputs['Base Color'])
                group.links.new(node_input.outputs['Color'], BlenderMaterials.__getSubsurfaceColor(node_principled))
                group.links.new(node_input.outputs['Normal'], node_principled.inputs['Normal'])
                group.links.new(node_input.outputs['Normal'], node_translucent.inputs['Normal'])
                group.links.new(node_principled.outputs[0], node_mix.inputs[1])
                group.links.new(node_translucent.outputs[0], node_mix.inputs[2])
                group.links.new(node_mix.outputs[0], node_output.inputs[0])
            else:
                node_diffuse = BlenderMaterials.__nodeDiffuse(group.nodes, 0.0, -242, 90)
                node_trans   = BlenderMaterials.__nodeTranslucent(group.nodes, -242, -46)
                node_glossy  = BlenderMaterials.__nodeGlossy(group.nodes, (1,1,1,1), 0.5, 'BECKMANN', -42, -54)
                node_mixOne  = BlenderMaterials.__nodeMixShader(group.nodes, 0.4, -35, 90)
                node_mixTwo  = BlenderMaterials.__nodeMixShader(group.nodes, 0.2, 175, 90)

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

    # **********************************************************************************
    def createBlenderNodeGroups():
        BlenderMaterials.usePrincipledShader = BlenderMaterials.__hasPrincipledShader and Options.usePrincipledShaderWhenAvailable

        BlenderMaterials.__createBlenderDistanceToCenterNodeGroup()
        BlenderMaterials.__createBlenderVectorElementPowerNodeGroup()
        BlenderMaterials.__createBlenderConvertToNormalsNodeGroup()
        BlenderMaterials.__createBlenderConcaveWallsNodeGroup()
        BlenderMaterials.__createBlenderSlopeTextureNodeGroup()

        # Originally based on ideas from https://www.youtube.com/watch?v=V3wghbZ-Vh4
        # "Create your own PBR Material [Fixed!]" by BlenderGuru
        # Updated with Principled Shader, if available
        BlenderMaterials.__createBlenderFresnelNodeGroup()
        BlenderMaterials.__createBlenderReflectionNodeGroup()
        BlenderMaterials.__createBlenderDielectricNodeGroup()

        BlenderMaterials.__createBlenderLegoStandardNodeGroup()
        BlenderMaterials.__createBlenderLegoTransparentNodeGroup()
        BlenderMaterials.__createBlenderLegoTransparentFluorescentNodeGroup()
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

        # Find the appropriate mesh edges and make them sharp (i.e. not smooth)
        for meshEdge in bm.edges:
            v0 = meshEdge.verts[0].index
            v1 = meshEdge.verts[1].index
            if (v0, v1) in edgeIndices:
                # Make edge sharp
                meshEdge.smooth = False

        # Set bevel weights
        if bpy.app.version < (4, 0, 0):
            # Blender 3
            # Find layer for bevel weights
            if 'BevelWeight' in bm.edges.layers.bevel_weight:
                bwLayer = bm.edges.layers.bevel_weight['BevelWeight']
            elif '' in bm.edges.layers.bevel_weight:
                bwLayer = bm.edges.layers.bevel_weight['']
            else:
                bwLayer = None

            for meshEdge in bm.edges:
                v0 = meshEdge.verts[0].index
                v1 = meshEdge.verts[1].index
                if (v0, v1) in edgeIndices:
                    # Add bevel weight
                    if bwLayer is not None:
                        meshEdge[bwLayer] = 1.0

        return edgeIndices

# Commented this next section out as it fails for certain pieces.

        # Look for any pair of colinear edges emanating from a single vertex, where each edge is connected to exactly one face.
        # Subdivide the longer edge to include the shorter edge's vertex.
        # Repeat until there's nothing left to subdivide.
        # This helps create better (more manifold) geometry in general, and in particular solves issues with technic pieces with holes.
#        verts = set(bm.verts)
#
#        while(verts):
#            v = verts.pop()
#            edges = [e for e in v.link_edges if len(e.link_faces) == 1]
#            for e1, e2 in itertools.combinations(edges, 2):
#
#                # ensure e1 is always the longer edge
#                if e1.calc_length() < e2.calc_length():
#                    e1, e2 = e2, e1
#
#                v1 = e1.other_vert(v)
#                v2 = e2.other_vert(v)
#                vec1 = v1.co - v.co
#                vec2 = v2.co - v.co
#
#                # test for colinear
#                if vec1.angle(vec2) < 0.02:
#                    old_face = e1.link_faces[0]
#                    new_verts = old_face.verts[:]
#
#                    e2.smooth &= e1.smooth
#                    if bwLayer is not None:
#                        e2[bwLayer] = max(e1[bwLayer], e2[bwLayer])
#
#                    # insert the shorter edge's vertex
#                    i = new_verts.index(v)
#                    i1 = new_verts.index(v1)
#                    if i1 - i in [1, -1]:
#                        new_verts.insert(max(i,i1), v2)
#                    else:
#                        new_verts.insert(0, v2)
#
#                    # create a new face that includes the newly inserted vertex
#                    new_face = bm.faces.new(new_verts)
#
#                    # copy material to new face
#                    new_face.material_index = old_face.material_index
#
#                    # copy metadata to the new edge
#                    for e in v2.link_edges:
#                        if e.other_vert(v2) is v1:
#                            e.smooth &= e1.smooth
#                            if bwLayer is not None:
#                                e[bwLayer] = max(e1[bwLayer], e[bwLayer])
#
#                    # delete the old edge
#                    deleteEdge(bm, [e1])
#
#                    # re-check the vertices we modified
#                    verts.add(v)
#                    verts.add(v2)
#                    break

        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

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
parent = None
attach_points = []
children = []
partsHierarchy = {}
macro_name = None
macros = {}

# **************************************************************************************
def parseParentsFile(file):
    global parent
    global attach_points
    global children
    global partsHierarchy
    global macro_name
    global macros

    # See https://stackoverflow.com/a/53870514
    number_pattern = "[+-]?((\d+(\.\d*)?)|(\.\d+))"
    pattern = "(" + number_pattern + ")(.*)"
    compiled = re.compile(pattern)

    def number_split(s):
        match = compiled.match(s)
        if match is None:
            return None, s
        groups = match.groups()
        return groups[0], groups[-1].strip()

    parent = None
    attach_points = []
    children = []
    partsHierarchy = {}
    macro_name = None
    macros = {}

    def finishParent():
        global parent
        global attach_points
        global children
        global partsHierarchy
        global macro_name

        if macro_name:
            macros[macro_name] = children
            # print("Adding macro ", macro_name)
            parent = None
            attach_points = []
            children = []
            macro_name = None

        if parent:
            partsHierarchy[parent] = (attach_points, children)
            parent = None
            attach_points = []
            children = []
            macro_name = None

    with open(file) as f:
        lines = f.readlines() # list containing lines of file

        line_number = 0
        for line in lines:
            line_number += 1
            line = line.strip() # remove leading/trailing white spaces
            line = line.split("#")[0]
            if line:
                line = line.strip()
                original_line = line
                if line.startswith("Group "):
                    # Found group definition
                    finishParent()
                    macro_name = line[6:].strip().strip(":")
                    # print("Found group definition ", macro_name)
                    continue
                if line.startswith("Parent "):
                    # Found parent definition
                    finishParent()
                    parent = line[7:].strip().strip(":")
                    # print("Found parent definition ", parent)
                    continue
                if line in macros:
                    # found instance of a macro
                    # add children to definition
                    children += macros[line]
                    continue

                # check for three floating point numbers of an attach point
                number1, line = number_split(line)
                if number1:
                    number3 = None
                    number2, line = number_split(line)
                    if number2:
                        number3, line = number_split(line)
                    if number3:
                        # Got three numbers for an attach point
                        try:
                            attachPoint = (float(number1), float(number2), float(number3))
                        except:
                            attachPoint = None
                        if attachPoint:
                            # Attach point
                            attach_points.append(attachPoint)
                            continue
                        else:
                            debugPrint("ERROR: Bad attach point found on line %d" % (line_number,))
                            partsHierarchy = None
                            return

                # child part number?
                children.append(original_line)

    finishParent()
    # print("Macros:")
    # pprint(macros)
    # print("End of Macros")
    return


# **************************************************************************************
def setupImplicitParents():
    global globalScaleFactor

    if not Options.minifigHierarchy:
        return

    parseParentsFile(Options.scriptDirectory + '/parents.txt')
    # print(partsHierarchy)
    if not partsHierarchy:
        return

    bpy.context.view_layer.update()

    # create a set of the parent parts and a set of child parts from the partsHierarchy
    parentParts = set()
    childParts = set()
    for parent, childrenData in partsHierarchy.items():
        parentParts.add(parent)
        childParts.update(childrenData[1])

    # create a flat set of all interesting parts (parents and children together)
    interestingParts = set()
    interestingParts.update(parentParts)
    interestingParts.update(childParts)

    # print('Parent parts: %s' % (parentParts,))
    # print('Child parts: %s' % (childParts,))
    # print('Interesting parts: %s' % (interestingParts,))

    tolerance = globalScaleFactor * 5 # in LDraw units
    squaredTolerance = tolerance * tolerance
    # print(" Squared tolerance: %s" % (squaredTolerance,))

    # For each interesting mesh in the scene, remember the bare part number and the children
    parentMeshParts = {}        # bare part numbers of the parents
    childMeshParts = {}         # bare part numbers of the children
    parentableMeshes = {}       # interesting children
    lego_part_pattern = "([A-Za-z]?\d+)($|\D)"

    # for each object in the scene
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue

        name = obj.data.name
        if not name.startswith('Mesh_'):
            continue

        # skip 'Mesh_' and get part of name that is just digits (possibly with a letter in front)
        test_name = name[5:]
        if " - " in test_name:
            test_name = test_name.split(" - ",1)[1]

        partName = ''
        m = re.match(lego_part_pattern, test_name)
        if m:
            partName = m.group(1)

        # For each interesting parent mesh in the scene, remember the bare part number and the children
        if partName in parentParts:
            # remember the bare part number for each interesting mesh in the scene
            parentMeshParts[name] = partName

            # remember possible children of the mesh in the scene
            children = partsHierarchy.get(partName)
            if children:
                parentableMeshes[name] = children

        # For each interesting child mesh in the scene, remember the bare part number
        if partName in childParts:
            # remember the bare part number for each interesting mesh in the scene
            childMeshParts[name] = partName

    # Now, iterate through the objects in the scene and gather the interesting ones
    parentObjects = []
    childObjects = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        meshName = obj.data.name
        if meshName in parentMeshParts:
            parentObjects.append(obj)
            # print("Possible parent object %s has matrix %s" % (obj.name, obj.matrix_world))
        if meshName in childMeshParts:
            childObjects.append(obj)

    # for each interesting parent object
    for obj in parentObjects:
        meshName = obj.data.name
        childrenData = parentableMeshes.get(meshName)
        if not childrenData:
            continue
        # parentLocation = obj.matrix_world @ mathutils.Vector((0, 0, 0))
        # parentMatrixInverted = obj.matrix_world.inverted()
        # print("Looking for children of %s (at %s)" % (obj.name, parentLocation))

        slotLocations = []
        for slot in childrenData[0]:
            loc = obj.matrix_world @ (mathutils.Vector(slot) * globalScaleFactor)
            slotLocations.append(loc)
        # print(" Slot locations: %s" % (slotLocations,))

        # for each interesting child object
        for childObj in childObjects:
            childMeshName = childObj.data.name
            childPartName = childMeshParts[childMeshName]
            if childPartName not in childrenData[1]:
                continue
            childLocation = childObj.matrix_world.to_translation()
            # print("  Found possible child %s" % (childObj.name,))
            for slotLocation in slotLocations:
                # print("  Slot location:%s   Child Location:%s" % (slotLocation, childLocation))
                diff = slotLocation - childLocation
                squaredDistance = diff.length_squared
                # print("  location: %s (squared distance: %s)" % (childLocation, squaredDistance))
                if squaredDistance <= squaredTolerance:
                    temp = childObj.matrix_world
                    childObj.parent = obj
                    # childObj.matrix_parent_inverse = parentMatrixInverted
                    childObj.matrix_world = temp
                    # print("    Got it! Parent '%s' now has child '%s'" % (obj.name, childObj.name))

# **************************************************************************************
def slopeAnglesForPart(partName):
    """
    Gets the allowable slope angles for a given part.
    """
    global globalSlopeAngles

    # Check for a part number with or without a subsequent letter
    match = re.match(r'\D*(\d+)([A-Za-z]?)', partName)
    if match:
        partNumberWithoutLetter = match.group(1)
        partNumberWithLetter = partNumberWithoutLetter + match.group(2)

        if partNumberWithLetter in globalSlopeAngles:
            return globalSlopeAngles[partNumberWithLetter]

        if partNumberWithoutLetter in globalSlopeAngles:
            return globalSlopeAngles[partNumberWithoutLetter]

    return None

# **************************************************************************************
def isSlopeFace(slopeAngles, isGrainySlopeAllowed, faceVertices):
    """
    Checks whether a given face should receive a grainy slope material.
    """

    # Step 1: Ignore some faces (studs) when checking for a grainy face
    if not isGrainySlopeAllowed:
        return False

    # Step 2: Calculate angle of face normal to the ground
    faceNormal = (faceVertices[1] - faceVertices[0]).cross(faceVertices[2]-faceVertices[0])
    faceNormal.normalize()

    # Clamp value to range -1 to 1 (ensure we are in the strict range of the acos function, taking account of rounding errors)
    cosine = min(max(faceNormal.y, -1.0), 1.0)

    # Calculate angle of face normal to the ground (-90 to 90 degrees)
    angleToGroundDegrees = math.degrees(math.acos(cosine)) - 90

    # debugPrint("Angle to ground {0}".format(angleToGroundDegrees))

    # Step 3: Check angle of normal to ground is within one of the acceptable ranges for this part
    return any(c[0] <= angleToGroundDegrees <= c[1] for c in slopeAngles)

# **************************************************************************************
def createMesh(name, meshName, geometry):
    # Are there any points?
    if not geometry.points:
        return (None, False)

    newMeshCreated = False

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

            points = [p.to_tuple() for p in geometry.points]

            mesh.from_pydata(points, [], geometry.faces)

            if geometry.uvs and any(elem is not None for elem in geometry.uvs):
                mesh.uv_layers.new(name="lego_texture")

                # It seems that the only way to set UVs is via bmesh:
                bm = bmesh.new()
                bm.from_mesh(mesh)
                bm.faces.ensure_lookup_table()

                uv_layer = bm.loops.layers.uv[0]

                for f in bm.faces:
                    for l in f.loops:
                        if geometry.uvs[l.vert.index]:
                            # Sanity check
                            if l.vert.index < len(geometry.uvs):
                                l[uv_layer].uv = geometry.uvs[l.vert.index]
                            else:
                                printWarningOnce("Ooops! Something is wrong with the UVs")
                bm.to_mesh(mesh)

            mesh.validate()
            mesh.update()

            # Set a custom parameter to record the options used to create this mesh
            # Used for caching.
            mesh['customMeshOptions'] = Options.meshOptionsString()

            newMeshCreated = True

        # Create materials and assign material to each polygon
        if mesh.users == 0:
            assert len(mesh.polygons) == len(geometry.faces)
            assert len(geometry.faces) == len(geometry.faceInfo)

            slopeAngles = slopeAnglesForPart(name)
            isSloped = slopeAngles is not None
            for i, f in enumerate(mesh.polygons):
                faceInfo = geometry.faceInfo[i]
                isSlopeMaterial = isSloped and isSlopeFace(slopeAngles, faceInfo.isGrainySlopeAllowed, [geometry.points[j] for j in geometry.faces[i]])
                faceColour = faceInfo.faceColour
                # For debugging purposes, we can make sloped faces blue:
                # if isSlopeMaterial:
                #     faceColour = "1"
                material = BlenderMaterials.getMaterial(faceColour, isSlopeMaterial, faceInfo.textureMap.imageFilename if faceInfo.textureMap else None, faceInfo.parentDir)

                if material is not None:
                    if mesh.materials.get(material.name) is None:
                        mesh.materials.append(material)
                    f.material_index = mesh.materials.find(material.name)
                else:
                    printWarningOnce("Could not find material '{0}' in mesh '{1}'.".format(faceColour, name))

    # Cache mesh
    if newMeshCreated:
        geometry.mesh = mesh

    return (mesh, newMeshCreated)

# **************************************************************************************
def addModifiers(ob):
    global globalScaleFactor

    # Add Bevel modifier to each instance
    if Options.addBevelModifier:
        bevelModifier = ob.modifiers.new("Bevel", type='BEVEL')
        bevelModifier.width = Options.bevelWidth * globalScaleFactor
        bevelModifier.segments = 4
        bevelModifier.profile = 0.5
        bevelModifier.limit_method = 'WEIGHT'
        bevelModifier.use_clamp_overlap = True

    # Add edge split modifier to each instance
    if Options.edgeSplit:
        edgeModifier = ob.modifiers.new("Edge Split", type='EDGE_SPLIT')
        edgeModifier.use_edge_sharp = True
        edgeModifier.split_angle = math.radians(30.0)

# **************************************************************************************
def smoothShadingAndFreestyleEdges(ob):
    # We would like to avoid using bpy.ops functions altogether since it
    # slows down progressively as more objects are added to the scene, but
    # we have no choice but to use it here (a) for smoothing and (b) for
    # marking freestyle edges (no bmesh options exist currently). To minimise
    # the performance drop, we add one object only to the scene, smooth it,
    # then remove it again. Only at the end of the import process are all the
    # objects properly added to the scene.

    # Temporarily add object to scene
    linkToScene(ob)

    # Select object
    selectObject(ob)

    # Smooth shading
    if Options.smoothShading:
        # Smooth the mesh
        bpy.ops.object.shade_smooth()

    if Options.instructionsLook:
        # Mark all sharp edges as freestyle edges
        me = bpy.context.object.data
        for e in me.edges:
            e.use_freestyle_mark = e.use_edge_sharp

    # Deselect object
    deselectObject(ob)

    # Remove object from scene
    unlinkFromScene(ob)


# **************************************************************************************
def createBlenderObjectsFromNode(node,
                                 localMatrix,
                                 name,
                                 topLevelNode,
                                 realColourName=Options.defaultColour,
                                 blenderParentTransform=Math.identityMatrix,
                                 localToWorldSpaceMatrix=Math.identityMatrix,
                                 blenderNodeParent=None,
                                 textureMap=None,
                                 textureMapMatrix=None):
    """
    Creates a Blender Object for the node given and (recursively) for all it's children as required.
    Creates and optimises the mesh for each object too.
    """

    global globalBrickCount
    global globalObjectsToAdd
    global globalWeldDistance
    global globalPoints

    ob = None

    if node.isBlenderObjectNode():
        ourColourName = LDrawNode.resolveColour(node.colourName, realColourName)
        meshName, geometry = node.getBlenderGeometry(ourColourName, name, textureMap, textureMapMatrix, topLevelNode)
        mesh, newMeshCreated = createMesh(name, meshName, geometry)

        # Format a name for the Blender Object
        if Options.numberNodes:
            blenderName = str(globalBrickCount).zfill(5) + "_" + name
        else:
            blenderName = name
        globalBrickCount = globalBrickCount + 1

        # Create Blender Object
        ob = bpy.data.objects.new(blenderName, mesh)
        ob.matrix_local = blenderParentTransform @ localMatrix

        if newMeshCreated:
            # Use bevel weights (added to sharp edges) - Only available for Blender version < 3.4
            if hasattr(ob.data, "use_customdata_edge_bevel"):
                ob.data.use_customdata_edge_bevel = True
            else:
                # Not needed in Blender 4
                if bpy.app.version < (4, 0, 0):
                    # Add to scene
                    linkToScene(ob)

                    # Blender 3.4 removed 'ob.data.use_customdata_edge_bevel', so this seems to be the alternative:
                    # See https://blender.stackexchange.com/a/270716
                    area_type = 'VIEW_3D' # change this to use the correct Area Type context you want to process in
                    areas  = [area for area in bpy.context.window.screen.areas if area.type == area_type]

                    if len(areas) <= 0:
                        raise Exception(f"Make sure an Area of type {area_type} is open or visible on your screen!")
                    selectObject(ob)
                    bpy.ops.object.mode_set(mode='EDIT')

                    with bpy.context.temp_override(
                        window=bpy.context.window,
                        area=areas[0],
                        regions=[region for region in areas[0].regions if region.type == 'WINDOW'][0],
                        screen=bpy.context.window.screen):
                        bpy.ops.mesh.customdata_bevel_weight_edge_add()
                    bpy.ops.object.mode_set(mode='OBJECT')

                    unlinkFromScene(ob)

        # The lines out of an empty shown in the viewport are scaled to a reasonable size
        ob.empty_display_size = 250.0 * globalScaleFactor

        # Mark object as transparent if any polygon is transparent
        ob["Lego.isTransparent"] = False
        if mesh is not None:
            for faceInfo in geometry.faceInfo:
                material = BlenderMaterials.getMaterial(faceInfo.faceColour, False, faceInfo.textureMap.imageFilename if faceInfo.textureMap else None, faceInfo.parentDir)
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

        # debugPrint("NAME = {0}".format(name))

        # Add light to light bricks
        if (name in globalLightBricks):
            lights = bpy.data.lights
            lamp_data = lights.new(name="LightLamp", type='POINT')
            lamp_data.shadow_soft_size = 0.05
            lamp_data.use_nodes = True
            emission_node = lamp_data.node_tree.nodes.get('Emission')
            if emission_node:
                emission_node.inputs['Color'].default_value = globalLightBricks[name]
                emission_node.inputs['Strength'].default_value = 100.0
            lamp_object = bpy.data.objects.new(name="LightLamp", object_data=lamp_data)
            lamp_object.location = (-0.27, 0.0, -0.18)

            addNodeToParentWithGroups(blenderNodeParent, [], lamp_object)

        if newMeshCreated:
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
            # Note: This doesn't work properly with a low distance value
            # So we scale up the vertices beforehand and scale them down afterwards
            for v in bm.verts:
                v.co = v.co * 1000

            if removeDoubles:
                bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=globalWeldDistance)

            for v in bm.verts:
                v.co = v.co / 1000

            # Recalculate normals
            if recalculateNormals:
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

            # Add sharp edges (and edge weights in Blender 3)
            edgeIndices = addSharpEdges(bm, geometry, name)

            bm.to_mesh(ob.data)

            # In Blender 4, set the edge weights (on ob.data rather than bm these days)
            if (bpy.app.version >= (4, 0, 0)) and edgeIndices:
                # Blender 4
                bevel_weight_attr = ob.data.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
                for idx, meshEdge in enumerate(bm.edges):
                    v0 = meshEdge.verts[0].index
                    v1 = meshEdge.verts[1].index
                    if (v0, v1) in edgeIndices:
                        bevel_weight_attr.data[idx].value = 1.0

            bm.clear()
            bm.free()

            # Show the sharp edges in Edit Mode
            for area in bpy.context.screen.areas:  # iterate through areas in current screen
                if area.type == 'VIEW_3D':
                    for space in area.spaces:  # iterate through spaces in current VIEW_3D area
                        if space.type == 'VIEW_3D':  # check if space is a 3D view
                            space.overlay.show_edge_sharp = True

            # Scale for Gaps
            if Options.gaps and node.file.isPart:
                # Distance between gaps is controlled by Options.realGapWidth
                # Gap height is set smaller than realGapWidth since empirically, stacked bricks tend
                # to be pressed more tightly together
                gapHeight = 0.33 * Options.realGapWidth
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
                    scaleFac.x = 1 - Options.realGapWidth * abs(objScale.x) / dim.x
                if dim.y != 0:
                    scaleFac.y = 1 - gapHeight            * abs(objScale.y) / dim.y
                if dim.z != 0:
                    scaleFac.z = 1 - Options.realGapWidth * abs(objScale.z) / dim.z

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

            smoothShadingAndFreestyleEdges(ob)

        # Keep track of all vertices in global space, for positioning the camera and/or root object at the end
        # Notice that we do this after scaling for Options.gaps
        if Options.positionObjectOnGroundAtOrigin or Options.positionCamera:
            if mesh and mesh.vertices:
                localTransform = localToWorldSpaceMatrix @ localMatrix
                points = [localTransform @ p.co for p in mesh.vertices]

                # Remember all the points
                globalPoints.extend(points)

        # Hide selection of studs
        if node.file.isStud:
            ob.hide_select = True

        # Add bevel and edge split modifiers as needed
        if mesh:
            addModifiers(ob)

    else:
        blenderParentTransform = blenderParentTransform @ localMatrix

    # Create children and parent them
    for childNode in node.file.childNodes:
        # Create sub-objects recursively
        childColourName = LDrawNode.resolveColour(childNode.colourName, realColourName)
        if textureMap:
            childTextureMap = textureMap
            childTextureMapMatrix = textureMapMatrix @ childNode.matrix
        else:
            childTextureMap = childNode.textureMap
            childTextureMapMatrix = Math.identityMatrix

        createBlenderObjectsFromNode(childNode, childNode.matrix, childNode.filename, False, childColourName, blenderParentTransform, localToWorldSpaceMatrix @ localMatrix, blenderNodeParent, childTextureMap, childTextureMapMatrix)

    return ob

# **************************************************************************************
def addFileToCache(relativePath, name):
    """Loads and caches an LDraw file in the cache of files"""

    file = LDrawFile(relativePath, False, "", None, True)
    CachedFiles.add(name, file)
    return True

# **************************************************************************************
def setupLineset(lineset, thickness, group):
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
    lineset.select_by_collection = True
    lineset.collection = bpy.data.collections[bpy.data.collections.find(group)]

    # Set line color
    lineset.linestyle.color = (0.0, 0.0, 0.0)

    # Set material to override color
    if 'LegoMaterial' not in lineset.linestyle.color_modifiers:
        lineset.linestyle.color_modifiers.new('LegoMaterial', 'MATERIAL')

    # Use square caps
    lineset.linestyle.caps = 'SQUARE'       # Can be 'ROUND', 'BUTT', or 'SQUARE'

    # Draw inside the edge of the object
    lineset.linestyle.thickness_position = 'INSIDE'

    # Set Thickness
    lineset.linestyle.thickness = thickness

# **************************************************************************************
def setupRealisticLook():
    scene = bpy.context.scene
    render = scene.render

    # Use cycles render
    scene.render.engine = 'CYCLES'

    # Add environment texture for world
    if Options.addWorldEnvironmentTexture:
        scene.world.use_nodes = True
        nodes = scene.world.node_tree.nodes
        links = scene.world.node_tree.links
        worldNodeNames = [node.name for node in scene.world.node_tree.nodes]

        if "LegoEnvMap" in worldNodeNames:
            env_tex = nodes["LegoEnvMap"]
        else:
            env_tex          = nodes.new('ShaderNodeTexEnvironment')
            env_tex.location = (-250, 300)
            env_tex.name     = "LegoEnvMap"
            env_tex.image    = bpy.data.images.load(Options.scriptDirectory + "/background.exr", check_existing=True)

        if "Background" in worldNodeNames:
            background = nodes["Background"]
            links.new(env_tex.outputs[0],background.inputs[0])
    else:
        scene.world.color = (1.0, 1.0, 1.0)

    if Options.setRenderSettings:
        useDenoising(scene, True)

        if (scene.cycles.samples < 400):
            scene.cycles.samples = 400
        if (scene.cycles.diffuse_bounces < 20):
            scene.cycles.diffuse_bounces = 20
        if (scene.cycles.glossy_bounces < 20):
            scene.cycles.glossy_bounces = 20

    # Check layer names to see if we were previously rendering instructions and change settings back.
    layerNames = getLayerNames(scene)
    if ("SolidBricks" in layerNames) or ("TransparentBricks" in layerNames):
        render.use_freestyle = False

        # Change camera back to Perspective
        if scene.camera is not None:
            scene.camera.data.type = 'PERSP'

        # For Blender Render, reset to opaque background (Not available in Blender 3.5.1 or higher.)
        if hasattr(render, "alpha_mode"):
            render.alpha_mode = 'SKY'

        # Turn off cycles transparency
        scene.cycles.film_transparent = False

        # Get the render/view layers we are interested in:
        layers = getLayers(scene)

        # If we have previously added render layers for instructions look, re-enable any disabled render layers
        for i in range(len(layers)):
            layers[i].use = True

        # Un-name SolidBricks and TransparentBricks layers
        if "SolidBricks" in layerNames:
            layers.remove(layers["SolidBricks"])

        if "TransparentBricks" in layerNames:
            layers.remove(layers["TransparentBricks"])

        # Re-enable all layers
        for i in range(len(layers)):
            layers[i].use = True

        # Create Compositing Nodes
        scene.use_nodes = True

        # If scene nodes exist for compositing instructions look, remove them
        nodeNames = [node.name for node in scene.node_tree.nodes]
        if "Solid" in nodeNames:
           scene.node_tree.nodes.remove(scene.node_tree.nodes["Solid"])

        if "Trans" in nodeNames:
           scene.node_tree.nodes.remove(scene.node_tree.nodes["Trans"])

        if "Z Combine" in nodeNames:
            scene.node_tree.nodes.remove(scene.node_tree.nodes["Z Combine"])

        # Set up standard link from Render Layers to Composite
        if "Render Layers" in nodeNames:
            if "Composite" in nodeNames:
                rl = scene.node_tree.nodes["Render Layers"]
                zCombine = scene.node_tree.nodes["Composite"]

                links = scene.node_tree.links
                links.new(rl.outputs[0], zCombine.inputs[0])

    removeCollection('Black Edged Bricks Collection')
    removeCollection('White Edged Bricks Collection')
    removeCollection('Solid Bricks Collection')
    removeCollection('Transparent Bricks Collection')

# **************************************************************************************
def removeCollection(name, remove_collection_objects=False):
    coll = bpy.data.collections.get(name)
    if coll:
        if remove_collection_objects:
            obs = [o for o in coll.objects if o.users == 1]
            while obs:
                bpy.data.objects.remove(obs.pop())

        bpy.data.collections.remove(coll)

# **************************************************************************************
def createCollection(scene, name):
    if bpy.data.collections.find(name) < 0:
        # Create collection
        bpy.data.collections.new(name)
        # Add collection to scene
        scene.collection.children.link(bpy.data.collections[name])

# **************************************************************************************
def setupInstructionsLook():
    global globalHasCollections

    scene = bpy.context.scene
    render = scene.render
    render.use_freestyle = True

    # Use Blender Eevee (or Eevee Next) for instructions look
    try:
        render.engine = 'BLENDER_EEVEE'
    except:
        render.engine = 'BLENDER_EEVEE_NEXT'

    # Change camera to Orthographic
    if scene.camera is not None:
        scene.camera.data.type = 'ORTHO'

    # For Blender Render, set transparent background. (Not available in Blender 3.5.1 or higher.)
    if hasattr(render, "alpha_mode"):
        render.alpha_mode = 'TRANSPARENT'

    # Turn on cycles transparency
    scene.cycles.film_transparent = True

    # Increase max number of transparency bounces to at least 80
    # This avoids artefacts when multiple transparent objects are behind each other
    if scene.cycles.transparent_max_bounces < 80:
        scene.cycles.transparent_max_bounces = 80

    # Add collections / groups, if not already present
    if globalHasCollections:
        createCollection(scene, 'Black Edged Bricks Collection')
        createCollection(scene, 'White Edged Bricks Collection')
        createCollection(scene, 'Solid Bricks Collection')
        createCollection(scene, 'Transparent Bricks Collection')
    else:
        if bpy.data.groups.find('Black Edged Bricks Collection') < 0:
            bpy.data.groups.new('Black Edged Bricks Collection')
        if bpy.data.groups.find('White Edged Bricks Collection') < 0:
            bpy.data.groups.new('White Edged Bricks Collection')

    # Find or create the render/view layers we are interested in:
    layers = getLayers(scene)

    # Remember current view layer
    current_view_layer = bpy.context.view_layer

    # Add layers as needed
    layerNames = list(map((lambda x: x.name), layers))
    if "SolidBricks" not in layerNames:
        bpy.ops.scene.view_layer_add()

        layers[-1].name = "SolidBricks"
        layers[-1].use = True
        layerNames.append("SolidBricks")
    solidLayer = layerNames.index("SolidBricks")

    if "TransparentBricks" not in layerNames:
        bpy.ops.scene.view_layer_add()

        layers[-1].name = "TransparentBricks"
        layers[-1].use = True
        layerNames.append("TransparentBricks")
    transLayer = layerNames.index("TransparentBricks")

    # Restore current view layer
    bpy.context.window.view_layer = current_view_layer

    # Use Z layer (defaults to off in Blender 3.5.1)
    if hasattr(layers[transLayer], "use_pass_z"):
        layers[transLayer].use_pass_z = True
    if hasattr(layers[solidLayer], "use_pass_z"):
        layers[solidLayer].use_pass_z = True

    # Disable any render/view layers that are not needed
    for i in range(len(layers)):
        if i not in [solidLayer, transLayer]:
            layers[i].use = False

    layers[solidLayer].use = True
    layers[transLayer].use = True

    # Include or exclude collections for each layer
    for collection in layers[solidLayer].layer_collection.children:
        collection.exclude = collection.name != 'Solid Bricks Collection'
    for collection in layers[transLayer].layer_collection.children:
        collection.exclude = collection.name != 'Transparent Bricks Collection'

    #layers[solidLayer].layer_collection.children['Black Edged Bricks Collection'].exclude = True
    #layers[solidLayer].layer_collection.children['White Edged Bricks Collection'].exclude = True
    #layers[solidLayer].layer_collection.children['Solid Bricks Collection'].exclude = False
    #layers[solidLayer].layer_collection.children['Transparent Bricks Collection'].exclude = True

    #layers[transLayer].layer_collection.children['Black Edged Bricks Collection'].exclude = True
    #layers[transLayer].layer_collection.children['White Edged Bricks Collection'].exclude = True
    #layers[transLayer].layer_collection.children['Solid Bricks Collection'].exclude = True
    #layers[transLayer].layer_collection.children['Transparent Bricks Collection'].exclude = False

    # Move each part to appropriate collection
    for object in scene.objects:
        isTransparent = False
        if "Lego.isTransparent" in object:
            isTransparent = object["Lego.isTransparent"]

            # Add objects to the appropriate layers
            if isTransparent:
                linkToCollection('Transparent Bricks Collection', object)
            else:
                linkToCollection('Solid Bricks Collection', object)

            # Add object to the appropriate group
            if object.data != None:
                colour = object.data.materials[0].diffuse_color

                # Dark colours have white lines
                if LegoColours.isDark(colour):
                    linkToCollection('White Edged Bricks Collection', object)
                else:
                    linkToCollection('Black Edged Bricks Collection', object)

    # Find or create linesets
    solidBlackLineset = None
    solidWhiteLineset = None
    transBlackLineset = None
    transWhiteLineset = None

    for lineset in layers[solidLayer].freestyle_settings.linesets:
        if lineset.name == "LegoSolidBlackLines":
            solidBlackLineset = lineset
        if lineset.name == "LegoSolidWhiteLines":
            solidWhiteLineset = lineset

    for lineset in layers[transLayer].freestyle_settings.linesets:
        if lineset.name == "LegoTransBlackLines":
            transBlackLineset = lineset
        if lineset.name == "LegoTransWhiteLines":
            transWhiteLineset = lineset

    if solidBlackLineset == None:
        layers[solidLayer].freestyle_settings.linesets.new("LegoSolidBlackLines")
        solidBlackLineset = layers[solidLayer].freestyle_settings.linesets[-1]
        setupLineset(solidBlackLineset, 2.25, 'Black Edged Bricks Collection')
    if solidWhiteLineset == None:
        layers[solidLayer].freestyle_settings.linesets.new("LegoSolidWhiteLines")
        solidWhiteLineset = layers[solidLayer].freestyle_settings.linesets[-1]
        setupLineset(solidWhiteLineset, 2, 'White Edged Bricks Collection')
    if transBlackLineset == None:
        layers[transLayer].freestyle_settings.linesets.new("LegoTransBlackLines")
        transBlackLineset = layers[transLayer].freestyle_settings.linesets[-1]
        setupLineset(transBlackLineset, 2.25, 'Black Edged Bricks Collection')
    if transWhiteLineset == None:
        layers[transLayer].freestyle_settings.linesets.new("LegoTransWhiteLines")
        transWhiteLineset = layers[transLayer].freestyle_settings.linesets[-1]
        setupLineset(transWhiteLineset, 2, 'White Edged Bricks Collection')

    # Create Compositing Nodes
    scene.use_nodes = True

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

    if "Set Alpha" in scene.node_tree.nodes:
        setAlpha = scene.node_tree.nodes["Set Alpha"]
    else:
        setAlpha = scene.node_tree.nodes.new('CompositorNodeSetAlpha')
    setAlpha.inputs[1].default_value = 0.75

    composite = scene.node_tree.nodes["Composite"]
    composite.location = (950, 400)
    zCombine.location = (750, 500)
    transLayer.location = (300, 300)
    solidLayer.location = (300, 600)
    setAlpha.location = (580, 370)

    links = scene.node_tree.links
    links.new(solidLayer.outputs[0], zCombine.inputs[0])
    links.new(solidLayer.outputs[2], zCombine.inputs[1])
    links.new(transLayer.outputs[0], setAlpha.inputs[0])
    links.new(setAlpha.outputs[0], zCombine.inputs[2])
    links.new(transLayer.outputs[2], zCombine.inputs[3])
    links.new(zCombine.outputs[0], composite.inputs[0])

    # Blender 3 only: link the Z from the Z Combine to the composite. This is not present in Blender 4.
    if bpy.app.version < (4, 0, 0):
        links.new(zCombine.outputs[1], composite.inputs[2])


# **************************************************************************************
def iterateCameraPosition(camera, render, vcentre3d, moveCamera):

    global globalPoints

    bpy.context.view_layer.update()

    minX = sys.float_info.max
    maxX = -sys.float_info.max
    minY = sys.float_info.max
    maxY = -sys.float_info.max

    # Calculate matrix to take 3d points into normalised camera space
    modelview_matrix = camera.matrix_world.inverted()

    get_depsgraph_method = getattr(bpy.context, "evaluated_depsgraph_get", None)
    if callable(get_depsgraph_method):
        depsgraph = get_depsgraph_method()
    else:
        depsgraph = bpy.context.depsgraph
    projection_matrix = camera.calc_matrix_camera(
        depsgraph,
        x=render.resolution_x,
        y=render.resolution_y,
        scale_x=render.pixel_aspect_x,
        scale_y=render.pixel_aspect_y)

    mp_matrix = projection_matrix @ modelview_matrix
    mpinv_matrix = mp_matrix.copy()
    mpinv_matrix.invert()

    isOrtho = bpy.context.scene.camera.data.type == 'ORTHO'

    # Convert 3d points to camera space, calculating the min and max extents in 2d normalised camera space.
    minDistToCamera = sys.float_info.max
    for point in globalPoints:
        p1 = mp_matrix @ mathutils.Vector((point.x, point.y, point.z, 1))
        if isOrtho:
            point2d = (p1.x, p1.y)
        elif abs(p1.w)<1e-8:
            continue
        else:
            point2d = (p1.x/p1.w, p1.y/p1.w)
        minX = min(point2d[0], minX)
        minY = min(point2d[1], minY)
        maxX = max(point2d[0], maxX)
        maxY = max(point2d[1], maxY)
        disttocamera = (point - camera.location).length
        minDistToCamera = min(minDistToCamera, disttocamera)

    #debugPrint("minX,maxX: " + ('%.5f' % minX) + "," + ('%.5f' % maxX))
    #debugPrint("minY,maxY: " + ('%.5f' % minY) + "," + ('%.5f' % maxY))

    # Calculate distance d from camera to centre of the model
    d = (vcentre3d - camera.location).length

    # Which axis is filling most of the display?
    largestSpan = max(maxX-minX, maxY-minY)

    # Force option to be in range
    if Options.cameraBorderPercent > 0.99999:
        Options.cameraBorderPercent = 0.99999

    # How far should the camera be away from the object?
    # Zoom in or out to make the coverage close to 1 (or 1-border if theres a border amount specified)
    scale = largestSpan/(2 - 2 * Options.cameraBorderPercent)
    desiredMinDistToCamera = scale * minDistToCamera

    # Adjust d to be the change in distance from the centre of the object
    offsetD = minDistToCamera - desiredMinDistToCamera

    # Calculate centre of object on screen
    centre2d = mathutils.Vector(((minX + maxX)*0.5, (minY+maxY)*0.5))

    # Get the forward vector of the camera
    tempMatrix = camera.matrix_world.copy()
    tempMatrix.invert()
    forwards4d = -tempMatrix[2]
    forwards3d = mathutils.Vector((forwards4d.x, forwards4d.y, forwards4d.z))

    # Transform the 2d centre of object back into 3d space
    if isOrtho:
        centre3d = mpinv_matrix @ mathutils.Vector((centre2d.x, centre2d.y, 0, 1))
        centre3d = mathutils.Vector((centre3d.x, centre3d.y, centre3d.z))

        # Move centre3d a distance d from the camera plane
        v = centre3d - camera.location
        dist = v.dot(forwards3d)
        centre3d = centre3d + (d - dist) * forwards3d
    else:
        centre3d = mpinv_matrix @ mathutils.Vector((centre2d.x, centre2d.y, -1, 1))
        centre3d = mathutils.Vector((centre3d.x / centre3d.w, centre3d.y / centre3d.w, centre3d.z / centre3d.w))

        # Make sure the 3d centre of the object is distance d from the camera location
        forwards = centre3d - camera.location
        forwards.normalize()
        centre3d = camera.location + d * forwards

    # Get the centre of the viewing area in 3d space at distance d from the camera
    # This is where we want to move the object to
    origin3d = camera.location + d * forwards3d

    #debugPrint("d: " + ('%.5f' % d))
    #debugPrint("camloc: " + ('%.5f' % camera.location.x) + "," + ('%.5f' % camera.location.y) + "," + ('%.5f' % camera.location.z))
    #debugPrint("forwards3d: " + ('%.5f' % forwards3d.x) + "," + ('%.5f' % forwards3d.y) + "," + ('%.5f' % forwards3d.z))
    #debugPrint("Origin3d: " + ('%.5f' % origin3d.x) + "," + ('%.5f' % origin3d.y) + "," + ('%.5f' % origin3d.z))
    #debugPrint("Centre3d: " + ('%.5f' % centre3d.x) + "," + ('%.5f' % centre3d.y) + "," + ('%.5f' % centre3d.z))

    # bpy.context.scene.cursor_location = centre3d
    # bpy.context.scene.cursor_location = origin3d

    if moveCamera:
        if isOrtho:
            offset3d = (centre3d - origin3d)

            camera.data.ortho_scale *= scale
        else:
            # How much do we want to move the camera?
            # We want to move the camera by the same amount as if we moved the centre of the object to the centre of the viewing area.
            # In practice, this is not completely accurate, since the perspective projection changes the objects silhouette in 2d space
            # when we move the camera, but it's close in practice. We choose to move it conservatively by 93% of our calculated amount,
            # a figure obtained by some quick practical observations of the convergence on a few test models.
            offset3d = 0.93 * (centre3d - origin3d) + offsetD * forwards3d
        # debugPrint("offset3d: " + ('%.5f' % offset3d.x) + "," + ('%.5f' % offset3d.y) + "," + ('%.5f' % offset3d.z) + " length:" + ('%.5f' % offset3d.length))
        # debugPrint("move by: " + ('%.5f' % offset3d.length))
        camera.location += mathutils.Vector((offset3d.x, offset3d.y, offset3d.z))
        return offset3d.length
    return 0.0

# **************************************************************************************
def getConvexHull(minPoints = 3):
    global globalPoints

    if len(globalPoints) >= minPoints:
        bm = bmesh.new()
        [bm.verts.new(v) for v in globalPoints]
        bm.verts.ensure_lookup_table()

        ret = bmesh.ops.convex_hull(bm, input=bm.verts, use_existing_faces=False)
        globalPoints = [vert.co.copy() for vert in ret["geom"] if isinstance(vert, bmesh.types.BMVert)]
        del ret
        bm.clear()
        bm.free()

# **************************************************************************************
def look_at_selected_object():
    areas = [area for area in bpy.context.window.screen.areas if area.type == 'VIEW_3D']
    if len(areas) > 0:
        context_override = bpy.context.copy()
        context_override['area'] = areas[0]
        context_override['region'] = [region for region in areas[0].regions if region.type == 'WINDOW'][0]
        with bpy.context.temp_override(**context_override):
            bpy.ops.view3d.view_selected()

# **************************************************************************************
def loadFromFile(context, filename, isFullFilepath=True):
    global globalCamerasToAdd
    global globalContext
    global globalScaleFactor
    global globalHasCollections

    # Set global scale factor
    # -----------------------
    #
    # 1. The size of Lego pieces:
    #
    # Lego scale: https://www.lugnet.com/~330/FAQ/Build/dimensions
    #
    #   1 Lego draw unit = 0.4 mm, in an idealised world.
    #
    # In real life, actual Lego pieces have been measured as 0.3993 mm +/- 0.0002,
    # which makes 0.4mm accurate enough for all practical purposes (The difference
    # being just 7 microns).
    #
    # 2. Blender coordinates:
    #
    # Blender reports coordinates in metres by default. So the
    # scale factor to convert from Lego units to Blender coordinates
    # is 0.0004.
    #
    # This calculation does not adjust for any gap between the pieces.
    # This is (optionally) done later in the calculations, where we
    # reduce the size of each piece by 0.2mm (default amount) to allow
    # for a small gap between pieces. This matches real piece sizes.
    #
    # 3. Blender Scene Unit Scale:
    #
    # Blender has a 'Scene Unit Scale' value which by default is set
    # to 1.0. By changing the 'Unit Scale' after import the size of
    # everything in the scene can be adjusted.

    globalScaleFactor = 0.0004 * Options.realScale
    globalWeldDistance = 0.01 * globalScaleFactor

    globalCamerasToAdd = []
    globalContext = context

    globalHasCollections = hasattr(bpy.data, "collections")

    # Make sure we have the latest configuration, including the latest ldraw directory
    # and the colours derived from that.
    Configure()
    LegoColours()
    Math()

    if Configure.ldrawInstallDirectory == "":
        printError("Could not find LDraw Part Library")
        return None

    # Clear caches
    CachedDirectoryFilenames.clear()
    CachedFiles.clear()
    CachedFilepaths.clear()
    CachedGeometry.clear()
    CachedTextureMaps.clear()
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
        addFileToCache("studtente-logo.dat", os.path.join("s", "teton.dat"))     # TENTE

    # Load and parse file to create geometry
    filename = os.path.expanduser(filename)

    debugPrint("Loading files")
    node = LDrawNode(filename, isFullFilepath, os.path.dirname(filename))
    node.load()
    # node.printBFC()

    if node.file.isModel:
        # Fix top level rotation from LDraw coordinate space to Blender coordinate space
        node.file.geometry.points = [Math.rotationMatrix @ p for p in node.file.geometry.points]
        node.file.geometry.edges  = [(Math.rotationMatrix @ e[0], Math.rotationMatrix @ e[1]) for e in node.file.geometry.edges]

        for childNode in node.file.childNodes:
            childNode.matrix = Math.rotationMatrix @ childNode.matrix


    # Switch to Object mode and deselect all
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')

    name = os.path.basename(filename)

    global globalBrickCount
    global globalObjectsToAdd
    global globalPoints

    globalBrickCount = 0
    globalObjectsToAdd = []
    globalPoints = []

    debugPrint("Creating NodeGroups")
    BlenderMaterials.createBlenderNodeGroups()

    # Create Blender objects from the loaded file
    debugPrint("Creating Blender objects")
    rootOb = createBlenderObjectsFromNode(node, node.matrix, name, topLevelNode=True)

    if not node.file.isModel:
        if rootOb.data:
            rootOb.data.transform(Math.rotationMatrix)

    scene  = bpy.context.scene
    camera = scene.camera
    render = scene.render

    debugPrint("Number of vertices: " + str(len(globalPoints)))

    # Take the convex hull of all the points in the scene (operation must have at least three vertices)
    # This results in far fewer points to consider when adjusting the object and/or camera position.
    getConvexHull()
    debugPrint("Number of convex hull vertices: " + str(len(globalPoints)))

    # Set camera type
    if scene.camera is not None:
        if Options.instructionsLook:
            scene.camera.data.type = 'ORTHO'
        else:
            scene.camera.data.type = 'PERSP'

    if globalPoints:
        # Calculate our bounding box in global coordinate space
        boundingBoxMin = globalPoints[0].copy()
        boundingBoxMax = globalPoints[0].copy()

        boundingBoxMin[0] = min(p[0] for p in globalPoints)
        boundingBoxMin[1] = min(p[1] for p in globalPoints)
        boundingBoxMin[2] = min(p[2] for p in globalPoints)
        boundingBoxMax[0] = max(p[0] for p in globalPoints)
        boundingBoxMax[1] = max(p[1] for p in globalPoints)
        boundingBoxMax[2] = max(p[2] for p in globalPoints)

        # Length of bounding box diagonal
        boundingBoxDistance = (boundingBoxMax - boundingBoxMin).length
        boundingBoxCentre = (boundingBoxMax + boundingBoxMin) * 0.5

        vcentre = (boundingBoxMin + boundingBoxMax) * 0.5
        offsetToCentreModel = mathutils.Vector((-vcentre.x, -vcentre.y, -boundingBoxMin.z))

        # Centre object only if root node is a model (i.e. not a single part)
        if Options.positionObjectOnGroundAtOrigin and node.file.isModel:
            debugPrint("Centre object")
            rootOb.location += offsetToCentreModel

            # Offset bounding box
            boundingBoxMin += offsetToCentreModel
            boundingBoxMax += offsetToCentreModel
            boundingBoxCentre += offsetToCentreModel

            # Offset all points
            globalPoints = [p + offsetToCentreModel for p in globalPoints]
            offsetToCentreModel = mathutils.Vector((0, 0, 0))

        # Position camera
        if camera and Options.positionCamera:
            debugPrint("Positioning Camera")

            camera.data.clip_start = 25 * globalScaleFactor            # 0.01 at normal scale
            camera.data.clip_end   = 250000 * globalScaleFactor        # 100 at normal scale

            # Set up a default camera position and rotation
            camera.location = mathutils.Vector((6.5, -6.5, 4.75))
            camera.location.normalize()
            camera.location = camera.location * boundingBoxDistance
            camera.rotation_mode = 'XYZ'
            camera.rotation_euler = mathutils.Euler((1.0471975803375244, 0.0, 0.7853981852531433), 'XYZ')

            # Must have at least three vertices to move the camera
            if len(globalPoints) >= 3:
                isOrtho = camera.data.type == 'ORTHO'
                if isOrtho:
                    iterateCameraPosition(camera, render, vcentre, True)
                else:
                    for i in range(20):
                        error = iterateCameraPosition(camera, render, vcentre, True)
                        if (error < 0.001):
                            break
            camera.location += offsetToCentreModel

    # Get existing object names
    sceneObjectNames = [x.name for x in scene.objects]

    # Remove default objects
    if Options.removeDefaultObjects:
        if "Cube" in sceneObjectNames:
            cube = scene.objects['Cube']
            if (cube.location.length < 0.001):
                unlinkFromScene(cube)

        if lightName in sceneObjectNames:
            light = scene.objects[lightName]
            lampVector = light.location - mathutils.Vector((4.076245307922363, 1.0054539442062378, 5.903861999511719))
            if (lampVector.length < 0.001):
                unlinkFromScene(light)

    # Finally add each object to the scene
    debugPrint("Adding {0} objects to scene".format(len(globalObjectsToAdd)))
    for ob in globalObjectsToAdd:
        linkToScene(ob)

    # Parent only once everything has been added to the scene, otherwise the matrix_world's are
    # sometimes not updated properly - some are erroneously still the identity matrix.
    setupImplicitParents()

    # Add cameras to the scene
    for ob in globalCamerasToAdd:
        cam = ob.createCameraNode()
        cam.parent = rootOb

    globalObjectsToAdd = []
    globalCamerasToAdd = []

    # Get existing object names
    sceneObjectNames = [x.name for x in scene.objects]

    # Add ground plane with white material
    if Options.addGroundPlane and not Options.instructionsLook:
        if "LegoGroundPlane" not in sceneObjectNames:
            addPlane((0,0,0), 100000 * globalScaleFactor)

            blenderName = "Mat_LegoGroundPlane"
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

            node = nodes.new('ShaderNodeBsdfDiffuse')
            node.location = 0, 5
            node.inputs['Color'].default_value = (1,1,1,1)
            node.inputs['Roughness'].default_value = 1.0

            out = nodes.new('ShaderNodeOutputMaterial')
            out.location = 200, 0
            links.new(node.outputs[0], out.inputs[0])

            for obj in bpy.context.selected_objects:
                obj.name = "LegoGroundPlane"
                if obj.data.materials:
                    obj.data.materials[0] = material
                else:
                    obj.data.materials.append(material)

    # Set to render at full resolution
    if Options.setRenderSettings:
        scene.render.resolution_percentage = 100

    # Setup scene as appropriate
    if Options.instructionsLook:
        setupInstructionsLook()
    else:
        setupRealisticLook()

    # Delete the temporary directory if there was one
    if Configure.tempDir:
        Configure.tempDir.cleanup()

    # Select the newly created root object
    bpy.ops.object.select_all(action='DESELECT')
    selectObject(rootOb, True)
    # Look at the selected object with the UI camera (not the camera object)
    if Options.positionCamera:
        look_at_selected_object()

    debugPrint("Load Done")
    return rootOb
