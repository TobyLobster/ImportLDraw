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
import itertools
import operator
from pprint import pprint

# **************************************************************************************
def matmul(a, b):
    """Perform matrix multiplication in a blender 2.7 and 2.8 safe way"""
    if isBlender28OrLater:
        return operator.matmul(a, b) # the same as writing a @ b, but parses ok in 2.7
    else:
        return a * b
        
# **************************************************************************************
def matvecmul(a, b):
    """Perform matrix multiplication in a blender 2.7 and 2.8 safe way"""
    if isBlender28OrLater:
        return operator.matmul(a, b) # the same as writing a @ b, but parses ok in 2.7
    else:
        return a * b

# **************************************************************************************
def linkToScene(ob):
    if isBlender28OrLater:
        if bpy.context.collection.objects.find(ob.name) < 0:
            bpy.context.collection.objects.link(ob)
    else:
        if bpy.context.scene.objects.find(ob.name) < 0:
            bpy.context.scene.objects.link(ob)
        
# **************************************************************************************
def linkToCollection(collectionName, ob):
    # Add object to the appropriate collection
    if hasCollections:
        if bpy.data.collections[collectionName].objects.find(ob.name) < 0:
            bpy.data.collections[collectionName].objects.link(ob)
    else:
        bpy.data.groups[collectionName].objects.link(ob)

# **************************************************************************************
def unlinkFromScene(ob):
    if isBlender28OrLater:
        if bpy.context.collection.objects.find(ob.name) >= 0:
            bpy.context.collection.objects.unlink(ob)
    else:
        if bpy.context.scene.objects.find(ob.name) >= 0:
            bpy.context.scene.objects.unlink(ob)

# **************************************************************************************
def selectObject(ob):
    if isBlender28OrLater:
        ob.select_set(state=True)
        bpy.context.view_layer.objects.active = ob
    else:
        ob.select = True
        bpy.context.scene.objects.active = ob

# **************************************************************************************
def deselectObject(ob):
    if isBlender28OrLater:
        ob.select_set(state=False)
        bpy.context.view_layer.objects.active = None
    else:
        ob.select = False
        bpy.context.scene.objects.active = None

# **************************************************************************************
def addPlane(location, size):
    if isBlender28OrLater:
        bpy.ops.mesh.primitive_plane_add(size=size, enter_editmode=False, location=location)
    else:
        bpy.ops.mesh.primitive_plane_add(radius=size, view_align=False, enter_editmode=False, location=location)

# **************************************************************************************
def useDenoising(scene, useDenoising):
    if hasattr(getLayers(scene)[0], "cycles"):
        getLayers(scene)[0].cycles.use_denoising = useDenoising

# **************************************************************************************
def getLayerNames(scene):
    return list(map((lambda x: x.name), getLayers(scene)))

# **************************************************************************************
def deleteEdge(bm, edge):
    if isBlender28OrLater:
        bmesh.ops.delete(bm, geom=edge, context='EDGES')
    else:
        bmesh.ops.delete(bm, geom=[edge], context=2)

# **************************************************************************************
def getLayers(scene):
    # Get the render/view layers we are interested in:
    if isBlender28OrLater:
        return scene.view_layers
    else:
        return scene.render.layers

# **************************************************************************************
def getDiffuseColor(color):
    if isBlender28OrLater:
        return color + (1.0,)
    else:
        return color

# **************************************************************************************
# **************************************************************************************
class Options:
    """User Options"""

    # Full filepath to ldraw folder. If empty, some standard locations are attempted
    ldrawDirectory     = r""            # Full filepath to the ldraw parts library (searches some standard locations if left blank)
    instructionsLook   = False          # Set up scene to look like Lego Instruction booklets
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
    importCameras      = True           # LeoCAD can specify cameras within the ldraw file format. Choose to load them or ignore them.
    positionObjectOnGroundAtOrigin = True   # Centre the object at the origin, sitting on the z=0 plane
    flattenHierarchy   = False          # All parts are under the root object - no sub-models
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
                         str(Options.addBevelModifier),
                         str(Options.bevelWidth)])

# **************************************************************************************
# Globals
globalBrickCount = 0
globalObjectsToAdd = []         # Blender objects to add to the scene
globalCamerasToAdd = []         # Camera data to add to the scene
globalContext = None
globalWeldDistance = 0.0005
globalPoints = []

isBlender28OrLater = None
hasCollections = None
if isBlender28OrLater:
    lightName = "Light"
else:
    lightName = "Lamp"


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
    '4885':{72}, 
    '6069':{72, 45}, 
    '6153':{(60, 70), (26, 34)}, 
    '6227':{45}, 
    '6270':{45}, 
    '13269':{(40, 63)}, 
    '13548':{45}, 
    '15571':{45}, 
    '18759':{-45}, 
    '22390':{(40, 55)}, 
    '22391':{(40, 55)}, 
    '22889':{-45}, 
    '28192':{45}, 
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
    '43708':{72}, 
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
for part in globalSlopeBricks:
    globalSlopeAngles[part] = {(c-margin, c+margin) if type(c) is not tuple else (min(c)-margin,max(c)+margin) for c in globalSlopeBricks[part]}

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

    def isDark(colour):
        R = colour[0]
        G = colour[1]
        B = colour[2]
        
        # Measure the perceived brightness of colour
        brightness = math.sqrt( 0.299*R*R + 0.587*G*G + 0.114*B*B )

        # Dark colours have white lines
        if brightness < 0.02:
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

        return FileSystem.__path_insensitive(path) or path

    def __path_insensitive(path):
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
            dirname = FileSystem.__path_insensitive(dirname)
            if not dirname:
                return

        # at this point, the directory exists but not the file

        try:  # we are expecting dirname to be a directory, but it could be a file
            files = CachedDirectoryFilenames.getCached(dirname)
            if files is None:
                files = os.listdir(dirname)
                CachedDirectoryFilenames.addToCache(dirname, files)
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

        return None


# **************************************************************************************
# **************************************************************************************
class CachedDirectoryFilenames:
    """Cached dictionary of directory filenames keyed by directory path"""

    __cache = {}        # Dictionary

    def getCached(key):
        if key in CachedDirectoryFilenames.__cache:
            return CachedDirectoryFilenames.__cache[key]
        return None

    def addToCache(key, value):
        CachedDirectoryFilenames.__cache[key] = value

    def clearCache():
        CachedDirectoryFilenames.__cache = {}


# **************************************************************************************
# **************************************************************************************
class CachedFiles:
    """Cached dictionary of LDrawFile objects keyed by filename"""

    __cache = {}        # Dictionary of exact filenames as keys, and file contents as values
    __lowercache = {}   # Dictionary of lowercase filenames as keys, and file contents as values

    def getCached(key):
        # Look for an exact match in the cache first
        if key in CachedFiles.__cache:
            return CachedFiles.__cache[key]
            
        # Look for a case-insensitive match next
        if key.lower() in CachedFiles.__lowercache:
            return CachedFiles.__lowercache[key.lower()]
        return None

    def addToCache(key, value):
        CachedFiles.__cache[key] = value
        CachedFiles.__lowercache[key.lower()] = value

    def clearCache():
        CachedFiles.__cache = {}
        CachedFiles.__lowercache = {}


# **************************************************************************************
# **************************************************************************************
class CachedGeometry:
    """Cached dictionary of LDrawGeometry objects"""

    __cache = {}        # Dictionary

    def getCached(key):
        if key in CachedGeometry.__cache:
            return CachedGeometry.__cache[key]
        return None

    def addToCache(key, value):
        CachedGeometry.__cache[key] = value

    def clearCache():
        CachedGeometry.__cache = {}

# **************************************************************************************
# **************************************************************************************
class FaceInfo:
    def __init__(self, faceColour, culling, windingCCW, isGrainySlopeAllowed):
        self.faceColour = faceColour
        self.culling = culling
        self.windingCCW = windingCCW
        self.isGrainySlopeAllowed = isGrainySlopeAllowed


# **************************************************************************************
# **************************************************************************************
class LDrawGeometry:
    """Stores the geometry for an LDrawFile"""

    def __init__(self):
        self.points = []
        self.faces = []
        self.faceInfo = []
        self.edges = []
        self.edgeIndices = []
        
    def parseFace(self, parameters, cull, ccw, isGrainySlopeAllowed):
        """Parse a face from parameters"""

        num_points = int(parameters[0])
        colourName = parameters[1]

        newPoints = []
        for i in range(num_points):
            blenderPos = matvecmul(Math.scaleMatrix, mathutils.Vector( (float(parameters[i * 3 + 2]),
                                                               float(parameters[i * 3 + 3]), 
                                                               float(parameters[i * 3 + 4])) ))
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
        self.faceInfo.append(FaceInfo(colourName, cull, ccw, isGrainySlopeAllowed))

    def parseEdge(self, parameters):
        """Parse an edge from parameters"""

        colourName = parameters[1]
        if colourName == "24":
            blenderPos1 = matvecmul(Math.scaleMatrix, mathutils.Vector( (float(parameters[2]),
                                                                float(parameters[3]), 
                                                                float(parameters[4])) ))
            blenderPos2 = matvecmul(Math.scaleMatrix, mathutils.Vector( (float(parameters[5]),
                                                                float(parameters[6]), 
                                                                float(parameters[7])) ))
            self.edges.append((blenderPos1, blenderPos2))

    def verify(self, face, numPoints):
        for i in face:
            assert i < numPoints
            assert i >= 0

    def appendGeometry(self, geometry, matrix, isStud, isStudLogo, parentMatrix, cull, invert):
        combinedMatrix = matmul(parentMatrix, matrix)
        isReflected = combinedMatrix.determinant() < 0.0
        reflectStudLogo = isStudLogo and isReflected

        fixedMatrix = matrix.copy()
        if reflectStudLogo:
            fixedMatrix = matmul(matrix, Math.reflectionMatrix)
            invert = not invert

        # Append face information
        pointCount = len(self.points)
        newFaceInfo = []
        for index, face in enumerate(geometry.faces):
            # Gather points for this face (and transform points)
            newPoints = []
            for i in face:
                newPoints.append(matvecmul(fixedMatrix, geometry.points[i]))

            # Add clockwise and/or anticlockwise sets of points as appropriate
            newFace = face.copy()
            for i in range(len(newFace)):
                newFace[i] += pointCount
            
            faceInfo = geometry.faceInfo[index]
            faceCCW = faceInfo.windingCCW != invert
            faceCull = faceInfo.culling and cull
            
            # If we are going to resolve ambiguous normals by "best guess" we will let 
            # Blender calculate that for us later. Just cull with arbitrary winding for now.
            if not faceCull:
                if Options.resolveAmbiguousNormals == "guess":
                    faceCull = True

            if faceCCW or not faceCull:
                self.points.extend(newPoints)
                self.faces.append(newFace)

                newFaceInfo.append(FaceInfo(faceInfo.faceColour, True, True, not isStud and faceInfo.isGrainySlopeAllowed))
                self.verify(newFace, len(self.points))

            if not faceCull:
                newFace = newFace.copy()
                pointCount += len(newPoints)
                for i in range(len(newFace)):
                    newFace[i] += len(newPoints)

            if not faceCCW or not faceCull:
                self.points.extend(newPoints[::-1])
                self.faces.append(newFace)
                
                newFaceInfo.append(FaceInfo(faceInfo.faceColour, True, True, not isStud and faceInfo.isGrainySlopeAllowed))
                self.verify(newFace, len(self.points))

        self.faceInfo.extend(newFaceInfo)
        assert len(self.faces) == len(self.faceInfo)

        # Append edge information
        newEdges = []
        for edge in geometry.edges:
            newEdges.append( (matvecmul(fixedMatrix, edge[0]), matvecmul(fixedMatrix, edge[1])) )
        self.edges.extend(newEdges)


# **************************************************************************************
# **************************************************************************************
class LDrawNode:
    """A node in the hierarchy. References one LDrawFile"""

    def __init__(self, filename, isFullFilepath, parentFilepath, colourName=Options.defaultColour, matrix=Math.identityMatrix, bfcCull=True, bfcInverted=False, isLSynthPart=False, isSubPart=False, isRootNode=True, groupNames=[]):
        self.filename       = filename
        self.isFullFilepath = isFullFilepath
        self.parentFilepath = parentFilepath
        self.matrix         = matrix
        self.colourName     = colourName
        self.bfcInverted    = bfcInverted
        self.bfcCull        = bfcCull
        self.file           = None
        self.isLSynthPart   = isLSynthPart
        self.isSubPart      = isSubPart
        self.isRootNode     = isRootNode
        self.groupNames     = groupNames.copy()

    def look_at(obj_camera, target, up_vector):
        if isBlender28OrLater:
            bpy.context.view_layer.update()
        else:
            bpy.context.scene.update()

        loc_camera = obj_camera.matrix_world.to_translation()

        #print("CamLoc = " + str(loc_camera[0]) + "," + str(loc_camera[1]) + "," + str(loc_camera[2]))
        #print("TarLoc = " + str(target[0]) + "," + str(target[1]) + "," + str(target[2]))
        #print("UpVec  = " + str(up_vector[0]) + "," + str(up_vector[1]) + "," + str(up_vector[2]))

        # back vector is a vector pointing from the target to the camera
        back = loc_camera - target;
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
        self.file = CachedFiles.getCached(self.filename)
        if self.file is None:
            # Not in cache, so load file
            self.file = LDrawFile(self.filename, self.isFullFilepath, self.parentFilepath, None, self.isSubPart)
            assert self.file is not None

            # Add the new file to the cache
            CachedFiles.addToCache(self.filename, self.file)

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
            combinedMatrix = matmul(parentMatrix, self.matrix)

            # Start with a copy of our file's geometry
            assert len(self.file.geometry.faces) == len(self.file.geometry.faceInfo)
            bakedGeometry = LDrawGeometry()
            bakedGeometry.appendGeometry(self.file.geometry, Math.identityMatrix, self.file.isStud, self.file.isStudLogo, combinedMatrix, self.bfcCull, self.bfcInverted)

            # Replaces the default colour 16 in our faceColours list with a specific colour
            for faceInfo in bakedGeometry.faceInfo:
                faceInfo.faceColour = LDrawNode.resolveColour(faceInfo.faceColour, ourColourName)

            # Append each child's geometry
            for child in self.file.childNodes:
                assert child.file is not None
                if not child.isBlenderObjectNode():
                    childColourName = LDrawNode.resolveColour(child.colourName, ourColourName)
                    childMeshName, bg = child.getBlenderGeometry(childColourName, basename, combinedMatrix, accumCull, accumInvert)

                    isStud = child.file.isStud
                    isStudLogo = child.file.isStudLogo
                    bakedGeometry.appendGeometry(bg, child.matrix, isStud, isStudLogo, combinedMatrix, self.bfcCull, self.bfcInverted)

            CachedGeometry.addToCache(key, bakedGeometry)
        assert len(bakedGeometry.faces) == len(bakedGeometry.faceInfo)
        return (meshName, bakedGeometry)


# **************************************************************************************
# **************************************************************************************
class LDrawCamera:
    """Data about a camera"""
    
    def __init__(self):
        self.vert_fov_degrees = 30.0
        self.near             = 25.0
        self.far              = 50000.0
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
        camera.hide = self.hidden
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
class LDrawFile:
    """Stores the contents of a single LDraw file.
    Specifically this represents an LDR, L3B, DAT or one '0 FILE' section of an MPD.
    Splits up an MPD file into '0 FILE' sections and caches them."""

    def __loadLegoFile(self, filepath, isFullFilepath, parentFilepath):
        # Resolve full filepath if necessary
        if isFullFilepath is False:
            if parentFilepath == "":
                parentDir = os.path.dirname(filepath)
            else:
                parentDir = os.path.dirname(parentFilepath)
            result = FileSystem.locate(filepath, parentDir)
            if result is None:
                printWarningOnce("Missing file {0}".format(filepath))
                return False
            filepath = result
        self.fullFilepath = filepath

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
            file = LDrawFile(sectionFilename, False, filepath, lines, False)
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

    def __init__(self, filename, isFullFilepath, parentFilepath, lines = None, isSubPart=False):
        """Loads an LDraw file (LDR, L3B, DAT or MPD)"""

        global globalCamerasToAdd
    
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

        isGrainySlopeAllowed = not self.isStud

        if self.lines is None:
            # Load the file into self.lines
            if not self.__loadLegoFile(self.filename, isFullFilepath, parentFilepath):
                return
        else:
            # We are loading a section of our parent document, so full filepath is that of the parent
            self.fullFilepath = parentFilepath

        # BFC = Back face culling. The rules are arcane and complex, but at least
        #       it's kind of documented: http://www.ldraw.org/article/415.html
        bfcLocalCull          = True
        bfcWindingCCW         = True
        bfcInvertNext         = False
        processingLSynthParts = False
        camera = LDrawCamera()

        currentGroupNames = []

        #debugPrint("Processing file {0}, isSubPart = {1}, found {2} lines".format(self.filename, self.isSubPart, len(self.lines)))

        for line in self.lines:
            parameters = line.strip().split()

            # Skip empty lines
            if len(parameters) == 0:
                continue
                
            # Pad with empty values to simplify parsing code
            while len(parameters) < 9:
                parameters.append("")

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
                    if parameters[2] == "CAMERA":
                        if Options.importCameras:
                            parameters = parameters[3:]
                            while( len(parameters) > 0):
                                if parameters[0] == "FOV":
                                    camera.vert_fov_degrees = float(parameters[1])
                                    parameters = parameters[2:]
                                elif parameters[0] == "ZNEAR":
                                    camera.near = Options.scale * float(parameters[1])
                                    parameters = parameters[2:]
                                elif parameters[0] == "ZFAR":
                                    camera.far = Options.scale * float(parameters[1])
                                    parameters = parameters[2:]
                                elif parameters[0] == "POSITION":
                                    camera.position = matvecmul(Math.scaleMatrix, mathutils.Vector((float(parameters[1]), float(parameters[2]), float(parameters[3]))))
                                    parameters = parameters[4:]
                                elif parameters[0] == "TARGET_POSITION":
                                    camera.target_position = matvecmul(Math.scaleMatrix, mathutils.Vector((float(parameters[1]), float(parameters[2]), float(parameters[3]))))
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
                                

            else:
                if self.bfcCertified is None:
                    self.bfcCertified = False

                self.isModel = (not self.isPart) and (not self.isSubPart)

                # Parse a File reference
                if parameters[0] == "1":
                    (x, y, z, a, b, c, d, e, f, g, h, i) = map(float, parameters[2:14])
                    (x, y, z) = matvecmul(Math.scaleMatrix, mathutils.Vector((x, y, z)))
                    localMatrix = mathutils.Matrix( ((a, b, c, x), (d, e, f, y), (g, h, i, z), (0, 0, 0, 1)) )

                    new_filename = " ".join(parameters[14:])
                    new_colourName = parameters[1]

                    det = localMatrix.determinant()
                    if det < 0:
                        bfcInvertNext = not bfcInvertNext
                    canCullChildNode = (self.bfcCertified or self.isModel) and bfcLocalCull and (det != 0)

                    newNode = LDrawNode(new_filename, False, self.fullFilepath, new_colourName, localMatrix, canCullChildNode, bfcInvertNext, processingLSynthParts, not self.isModel, False, currentGroupNames)
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

                    assert len(self.geometry.faces) == len(self.geometry.faceInfo)
                    self.geometry.parseFace(parameters, self.bfcCertified and bfcLocalCull, bfcWindingCCW, isGrainySlopeAllowed)
                    assert len(self.geometry.faces) == len(self.geometry.faceInfo)

                bfcInvertNext = False

        #debugPrint("File {0} is part = {1}, is subPart = {2}, isModel = {3}".format(filename, self.isPart, isSubPart, self.isModel))


# **************************************************************************************
# **************************************************************************************
class BlenderMaterials:
    """Creates and stores a cache of materials for Blender"""

    __material_list = {}
    __hasPrincipledShader = "ShaderNodeBsdfPrincipled" in [node.nodetype for node in getattr(bpy.types, "NODE_MT_category_SH_NEW_SHADER").category.items(None)]

    def __getGroupName(name):
        if Options.instructionsLook:
            return name + " Instructions"
        return name

    def __setBlenderRenderProperties(material, nodes, links, col):
        """Set Blender Internal Material Values."""

        if isBlender28OrLater:
            return

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
            mult = BlenderMaterials.__nodeMath(nodes, 'MULTIPLY', 200, -410);
            links.new(input.outputs[1], mult.inputs[0])
            links.new(mult.outputs[0], output.inputs[1])
        else:
            links.new(input.outputs[1], output.inputs[1])


    def __createNodeBasedMaterial(blenderName, col, isSlopeMaterial=False):
        """Set Cycles Material Values."""

        # Reuse current material if it exists, otherwise create a new material
        if bpy.data.materials.get(blenderName) is None:
            material = bpy.data.materials.new(blenderName)
        else:
            material = bpy.data.materials[blenderName]

        # Use nodes
        material.use_nodes = True

        if col is not None:
            colour = col["colour"] + (1.0,)
            material.diffuse_color = getDiffuseColor(col["colour"])

        if Options.instructionsLook:
            if not isBlender28OrLater:
                material.use_shadeless = True
                material.diffuse_intensity = 1.0
                material.translucency = 0
            else:
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
            BlenderMaterials.__setBlenderRenderProperties(material, nodes, links, col)

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
                BlenderMaterials.__createCyclesConcaveWalls(nodes, links, 0.2)

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

    def __nodeMix(nodes, factor, x, y):
        node = nodes.new('ShaderNodeMixShader')
        node.location = x, y
        node.inputs['Fac'].default_value = factor
        return node

    def __nodeOutput(nodes, x, y):
        node = nodes.new('ShaderNodeOutputMaterial')
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
        node.inputs['Subsurface'].default_value = subsurface
        node.inputs['Subsurface Radius'].default_value = mathutils.Vector( (sub_rad, sub_rad, sub_rad) )
        node.inputs['Metallic'].default_value = metallic
        node.inputs['Roughness'].default_value = roughness
        node.inputs['Clearcoat'].default_value = clearcoat
        node.inputs['Clearcoat Roughness'].default_value = clearcoat_roughness
        node.inputs['IOR'].default_value = ior
        node.inputs['Transmission'].default_value = transmission
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
            printWarningOnce("WARNING: Could not decode {0} to a colour".format(colourName))
            return None
        return {
            "name":         colourName,
            "colour":       linearRGBA[0:3],
            "alpha":        linearRGBA[3],
            "luminance":    0.0,
            "material":     "BASIC"
        }

    # **********************************************************************************
    def getMaterial(colourName, isSlopeMaterial):
        pureColourName = colourName
        if isSlopeMaterial:
            colourName = colourName + "_s"

        # If it's already in the cache, use that
        if (colourName in BlenderMaterials.__material_list):
            result = BlenderMaterials.__material_list[colourName]
            return result

        # Create a name for the material based on the colour
        if Options.instructionsLook:
            blenderName = "MatInst_{0}".format(colourName)
        elif Options.curvedWalls and not isSlopeMaterial:
            blenderName = "Material_{0}_c".format(colourName)
        else:
            blenderName = "Material_{0}".format(colourName)

        # If the name already exists in Blender, use that
        if Options.overwriteExistingMaterials is False:
            if blenderName in bpy.data.materials:
                return bpy.data.materials[blenderName]

        # Create new material
        col = BlenderMaterials.__getColourData(pureColourName)
        material = BlenderMaterials.__createNodeBasedMaterial(blenderName, col, isSlopeMaterial)

        if material is None:
            printWarningOnce("Could not create material for blenderName {0}".format(blenderName))

        # Add material to cache
        BlenderMaterials.__material_list[colourName] = material
        return material

    # **********************************************************************************
    def clearCache():
        BlenderMaterials.__material_list = {}

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
            group.outputs.new('NodeSocketShader','Shader')
        return (group, node_input, node_output)

    # **********************************************************************************
    def __createBlenderDistanceToCenterNodeGroup():
        if bpy.data.node_groups.get('Distance-To-Center') is None:
            debugPrint("createBlenderDistanceToCenterNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('Distance-To-Center', -930, 0, 240, 0, False)
            group.outputs.new('NodeSocketVectorDirection', 'Vector')

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
            group.links.new(node_vector_subtraction2.outputs['Vector'], node_output.inputs['Vector'])

    # **********************************************************************************
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
            group.inputs.new('NodeSocketFloat','Vector Length')
            group.inputs.new('NodeSocketFloat','Smoothing')
            group.inputs.new('NodeSocketFloat','Strength')
            group.inputs.new('NodeSocketVectorDirection','Normal')
            group.outputs.new('NodeSocketVectorDirection','Normal')

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

    # **********************************************************************************
    def __createBlenderSlopeTextureNodeGroup():
        if bpy.data.node_groups.get('Slope Texture') is None:
            debugPrint("createBlenderSlopeTextureNodeGroup #create")
            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup('Slope Texture', -530, 0, 300, 0, False)
            group.inputs.new('NodeSocketFloat', 'Strength')
            group.inputs.new('NodeSocketVectorDirection', 'Normal')
            group.outputs.new('NodeSocketVectorDirection', 'Normal')

            # create nodes
            node_texture_coordinate = BlenderMaterials.__nodeTexCoord(group.nodes, -300, 240)
            node_voronoi = BlenderMaterials.__nodeVoronoi(group.nodes, 3.0/Options.scale, -100, 155)
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

    # **********************************************************************************
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

    # **********************************************************************************
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
                if BlenderMaterials.usePrincipledShader:
                    node_main = BlenderMaterials.__nodePrincipled(group.nodes, 0.05, 0.05, 0.0, 0.1, 0.0, 0.0, 1.45, 0.0, 0, 0)
                    output_name = 'BSDF'
                    color_name = 'Base Color'
                    group.links.new(node_input.outputs['Color'],        node_main.inputs['Subsurface Color'])
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
                if BlenderMaterials.usePrincipledShader:
                    node_principled  = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 0.0, 0.05, 0.0, 0.0, 1.585, 1.0, 45, 340)
                    node_emission    = BlenderMaterials.__nodeEmission(group.nodes, 45, -160)
                    node_mix         = BlenderMaterials.__nodeMix(group.nodes, 0.03, 300, 290)
                    
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
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

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
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_noise = BlenderMaterials.__nodeNoiseTexture(group.nodes, 250, 2, 0.0, 45-770, 340-200)
                node_bump1 = BlenderMaterials.__nodeBumpShader(group.nodes, 1.0, 0.3, 45-366, 340-200)
                node_bump2 = BlenderMaterials.__nodeBumpShader(group.nodes, 1.0, 0.1, 45-184, 340-115)
                node_subtract = BlenderMaterials.__nodeMath(group.nodes, 'SUBTRACT', 45-570, 340-216)
                node_principled  = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 0.0, 0.4, 0.03, 0.0, 1.45, 0.0, 45, 340)
                node_mix = BlenderMaterials.__nodeMix(group.nodes, 0.8, 300, 290)
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
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketFloatFactor','Luminance')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            node_emit  = BlenderMaterials.__nodeEmission(group.nodes, -242, -123)
            node_mix   = BlenderMaterials.__nodeMix(group.nodes, 0.5, 0, 90)

            if BlenderMaterials.usePrincipledShader:
                node_main = BlenderMaterials.__nodePrincipled(group.nodes, 1.0, 0.05, 0.0, 0.5, 0.0, 0.03, 1.45, 0.0, -242, 154+240)
                group.links.new(node_input.outputs['Color'],     node_main.inputs['Subsurface Color'])
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
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

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
                node_mix       = BlenderMaterials.__nodeMix(group.nodes, 0.01, 0, 90)

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
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

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
                group.links.new(node_com_hsv.outputs['Color'], node_principled.inputs['Subsurface Color'])
                group.links.new(node_tex_coord.outputs['Object'], node_tex_wave.inputs['Vector'])
                group.links.new(node_tex_wave.outputs['Fac'], node_color_ramp.inputs['Fac'])
                group.links.new(node_color_ramp.outputs['Color'], node_multiply.inputs[1])
                group.links.new(node_multiply.outputs[0], node_com_hsv.inputs['V'])
                group.links.new(node_principled.outputs['BSDF'], node_output.inputs[0])
            else:
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

    # **********************************************************************************
    def __createBlenderLegoMetalNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Metal')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoMetalNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 90, 250, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_principled  = BlenderMaterials.__nodePrincipled(group.nodes, 0.0, 0.0, 0.8, 0.2, 0.0, 0.03, 1.45, 0.0, 310, 95)

                group.links.new(node_input.outputs['Color'], node_principled.inputs['Base Color'])
                group.links.new(node_input.outputs['Normal'], node_principled.inputs['Normal'])
                group.links.new(node_principled.outputs[0], node_output.inputs['Shader'])
            else:
                node_dielectric = BlenderMaterials.__nodeDielectric(group.nodes, 0.05, 0.2, 0.0, 1.46, -242, 0)
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

    # **********************************************************************************
    def __createBlenderLegoGlitterNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Glitter')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoGlitterNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 0, 410, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketColor','Glitter Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_voronoi     = BlenderMaterials.__nodeVoronoi(group.nodes, 100, -222, 310)
                node_gamma       = BlenderMaterials.__nodeGamma(group.nodes, 50, 0, 200)
                node_mix         = BlenderMaterials.__nodeMix(group.nodes, 0.05, 210, 90+25)
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

    # **********************************************************************************
    def __createBlenderLegoSpeckleNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Speckle')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoSpeckleNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 0, 410, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketColor','Speckle Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_voronoi     = BlenderMaterials.__nodeVoronoi(group.nodes, 50, -222, 310)
                node_gamma       = BlenderMaterials.__nodeGamma(group.nodes, 3.5, 0, 200)
                node_mix         = BlenderMaterials.__nodeMix(group.nodes, 0.05, 210, 90+25)
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

    # **********************************************************************************
    def __createBlenderLegoMilkyWhiteNodeGroup():
        groupName = BlenderMaterials.__getGroupName('Lego Milky White')
        if bpy.data.node_groups.get(groupName) is None:
            debugPrint("createBlenderLegoMilkyWhiteNodeGroup #create")

            # create a group
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -450, 0, 350, 0, True)
            group.inputs.new('NodeSocketColor','Color')
            group.inputs.new('NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_principled = BlenderMaterials.__nodePrincipled(group.nodes, 1.0, 0.05, 0.0, 0.5, 0.0, 0.03, 1.45, 0.0, 45-270, 340-210)
                node_translucent = BlenderMaterials.__nodeTranslucent(group.nodes, -225, -382)
                node_mix = BlenderMaterials.__nodeMix(group.nodes, 0.5, 65, -40)

                group.links.new(node_input.outputs['Color'], node_principled.inputs['Base Color'])
                group.links.new(node_input.outputs['Color'], node_principled.inputs['Subsurface Color'])
                group.links.new(node_input.outputs['Normal'], node_principled.inputs['Normal'])
                group.links.new(node_input.outputs['Normal'], node_translucent.inputs['Normal'])
                group.links.new(node_principled.outputs[0], node_mix.inputs[1])
                group.links.new(node_translucent.outputs[0], node_mix.inputs[2])
                group.links.new(node_mix.outputs[0], node_output.inputs[0])
            else:
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
def point_to_line_segment_dist_squared(p, a, b):
    ab = b - a
    ab_length_squared = ab.dot(ab)
    if (ab_length_squared < epsilon):
        t = 0.5
    else:
        ap = p - a
        t = ap.dot(ab) / ab_length_squared
        t = max(0, min(t, 1))
    c = p - (a + t * ab)
    return c.dot(c)

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
    if True in { c[0] <= angleToGroundDegrees <= c[1] for c in slopeAngles }:
        return True

    return False

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
                material = BlenderMaterials.getMaterial(faceColour, isSlopeMaterial)

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
    # Add Bevel modifier to each instance
    if Options.addBevelModifier:
        bevelModifier = ob.modifiers.new("Bevel", type='BEVEL')
        bevelModifier.width = Options.bevelWidth * Options.scale
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
                                 realColourName=Options.defaultColour, 
                                 blenderParentTransform=Math.identityMatrix, 
                                 localToWorldSpaceMatrix=Math.identityMatrix, 
                                 blenderNodeParent=None):
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
        meshName, geometry = node.getBlenderGeometry(ourColourName, name)
        mesh, newMeshCreated = createMesh(name, meshName, geometry)

        # Format a name for the Blender Object
        if Options.numberNodes:
            blenderName = str(globalBrickCount).zfill(5) + "_" + name
        else:
            blenderName = name
        globalBrickCount = globalBrickCount + 1

        # Create Blender Object
        ob = bpy.data.objects.new(blenderName, mesh)
        ob.matrix_local = matmul(blenderParentTransform, localMatrix)

        # Mark object as transparent if any polygon is transparent
        ob["Lego.isTransparent"] = False
        if mesh is not None:
            for faceInfo in geometry.faceInfo:
                material = BlenderMaterials.getMaterial(faceInfo.faceColour, False)
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
            lamp_data = bpy.data.lamps.new(name="LightLamp", type='POINT')
            lamp_data.shadow_soft_size = 0.05
            lamp_data.use_nodes = True
            emission_node = lamp_data.node_tree.nodes.get('Emission')
            if emission_node:
                emission_node.inputs['Color'].default_value = globalLightBricks[name]
                emission_node.inputs['Strength'].default_value = 100.0
            lamp_object = bpy.data.objects.new(name="LightLamp", object_data=lamp_data)
            lamp_object.location = (-0.27, 0.18, 0.0)
            
            addNodeToParentWithGroups(blenderNodeParent, [], lamp_object)

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
            bm.clear()
            bm.free()
            
            # Show the sharp edges in Edit Mode
            if isBlender28OrLater:
                for area in bpy.context.screen.areas:  # iterate through areas in current screen
                    if area.type == 'VIEW_3D':
                        for space in area.spaces:  # iterate through spaces in current VIEW_3D area
                            if space.type == 'VIEW_3D':  # check if space is a 3D view
                                space.overlay.show_edge_sharp = True
            else:
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

            smoothShadingAndFreestyleEdges(ob)

        # Keep track of all vertices in global space, for positioning the camera and/or root object at the end
        # Notice that we do this after scaling for Options.gaps
        if Options.positionObjectOnGroundAtOrigin or Options.positionCamera:
            if mesh and mesh.vertices:
                localTransform = matmul(localToWorldSpaceMatrix, localMatrix)
                points = [matvecmul(localTransform, p.co) for p in mesh.vertices]

                # Remember all the points                
                globalPoints.extend(points)

        # Hide selection of studs
        if node.file.isStud:
            ob.hide_select = True

        # Add bevel and edge split modifiers as needed
        if mesh:
            addModifiers(ob)
    else:
        blenderParentTransform = matmul(blenderParentTransform, localMatrix)

    # Create children and parent them
    for childNode in node.file.childNodes:
        # Create sub-objects recursively
        childColourName = LDrawNode.resolveColour(childNode.colourName, realColourName)
        createBlenderObjectsFromNode(childNode, childNode.matrix, childNode.filename, childColourName, blenderParentTransform, matmul(localToWorldSpaceMatrix, localMatrix), blenderNodeParent)

    return ob

# **************************************************************************************
def addFileToCache(relativePath, name):
    """Loads and caches an LDraw file in the cache of files"""

    file = LDrawFile(relativePath, False, "", None, True)
    CachedFiles.addToCache(name, file)
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
    if isBlender28OrLater:
        lineset.select_by_collection = True
        lineset.collection = bpy.data.collections[bpy.data.collections.find(group)]
    else:
        lineset.select_by_group = True
        lineset.group = bpy.data.groups[bpy.data.groups.find(group)]
    
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
        worldNodeNames = list(map((lambda x: x.name), scene.world.node_tree.nodes))

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
        if isBlender28OrLater:
            scene.world.color = (1.0, 1.0, 1.0)
        else:
            scene.world.horizon_color = (1.0, 1.0, 1.0)

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

        # For Blender Render, reset to opaque background
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

        # Move each part to appropriate scene layer
        if not isBlender28OrLater:
            for object in scene.objects:
                # For each lego object...
                if "Lego.isTransparent" in object:
                    # Turn on just the first scene layer
                    length = len(object.layers)
                    for i in range(length):
                        object.layers[i] = (i == 0)

        # Create Compositing Nodes
        scene.use_nodes = True

        # If scene nodes exist for compositing instructions look, remove them
        nodeNames = list(map((lambda x: x.name), scene.node_tree.nodes))
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


# **************************************************************************************
def setupInstructionsLook():
    scene = bpy.context.scene
    render = scene.render
    render.use_freestyle = True

    if isBlender28OrLater:
        # Use Blender Eevee for instructions look
        render.engine = 'BLENDER_EEVEE'
    else:
        # Use Blender render for instructions look
        render.engine = 'BLENDER_RENDER'

    # Change camera to Orthographic
    if scene.camera is not None:
        scene.camera.data.type = 'ORTHO'

    # For Blender Render, set transparent background
    render.alpha_mode = 'TRANSPARENT'

    # Turn on cycles transparency
    scene.cycles.film_transparent = True

    # Increase max number of transparency bounces to at least 80
    # This avoids artefacts when multiple transparent objects are behind each other
    if scene.cycles.transparent_max_bounces < 80:
        scene.cycles.transparent_max_bounces = 80

    # Add two groups, if not already present
    if hasCollections:
        if bpy.data.collections.find('Black Edged Bricks Collection') < 0:
            # Create collection
            bpy.data.collections.new('Black Edged Bricks Collection')
            # Add collection to scene
            scene.collection.children.link(bpy.data.collections['Black Edged Bricks Collection'])
        if bpy.data.collections.find('White Edged Bricks Collection') < 0:
            # Create collection
            bpy.data.collections.new('White Edged Bricks Collection')
            # Add collection to scene
            scene.collection.children.link(bpy.data.collections['White Edged Bricks Collection'])
        if bpy.data.collections.find('Solid Bricks Collection') < 0:
            # Create collection
            bpy.data.collections.new('Solid Bricks Collection')
            # Add collection to scene
            scene.collection.children.link(bpy.data.collections['Solid Bricks Collection'])
        if bpy.data.collections.find('Transparent Bricks Collection') < 0:
            # Create collection
            bpy.data.collections.new('Transparent Bricks Collection')
            # Add collection to scene
            scene.collection.children.link(bpy.data.collections['Transparent Bricks Collection'])

    else:
        if bpy.data.groups.find('Black Edged Bricks Collection') < 0:
            bpy.data.groups.new('Black Edged Bricks Collection')
        if bpy.data.groups.find('White Edged Bricks Collection') < 0:
            bpy.data.groups.new('White Edged Bricks Collection')

    # Find or create the render/view layers we are interested in:
    layers = getLayers(scene)

    layerNames = list(map((lambda x: x.name), layers))
    if "SolidBricks" not in layerNames:
        if isBlender28OrLater:
            bpy.ops.scene.view_layer_add()
        else:
            bpy.ops.scene.render_layer_add()

        layers[-1].name = "SolidBricks"
        layers[-1].use = True
        layerNames.append("SolidBricks")
    solidLayer = layerNames.index("SolidBricks")

    if "TransparentBricks" not in layerNames:
        if isBlender28OrLater:
            bpy.ops.scene.view_layer_add()
        else:
            bpy.ops.scene.render_layer_add()

        layers[-1].name = "TransparentBricks"
        layers[-1].use = True
        layerNames.append("TransparentBricks")
    transLayer = layerNames.index("TransparentBricks")

    # Disable any render/view layers that are not needed
    for i in range(len(layers)):
        if i not in [solidLayer, transLayer]:
            layers[i].use = False

    if isBlender28OrLater:
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
        
    else:
        # Enable two scene layers
        scene.layers[0] = True
        scene.layers[1] = True

        # Enable just the right scene layers in each of our two render layers
        length = len(layers[solidLayer].layers)
        for i in range(length):
            layers[solidLayer].layers[i] = (i == 0)

        length = len(layers[transLayer].layers)
        for i in range(length):
            layers[transLayer].layers[i] = (i == 1)

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
                length = len(object.layers)
                for i in range(length):
                    if isTransparent:
                        object.layers[i] = (i == 1)
                    else:
                        object.layers[i] = (i == 0)

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
def iterateCameraPosition(camera, render, vcentre3d, moveCamera):

    global globalPoints

    if isBlender28OrLater:
        bpy.context.view_layer.update()
    else:
        bpy.context.scene.update()
    
    minX = sys.float_info.max
    maxX = -sys.float_info.max
    minY = sys.float_info.max
    maxY = -sys.float_info.max
    
    # Calculate matrix to take 3d points into normalised camera space
    modelview_matrix = camera.matrix_world.inverted()
    
    if isBlender28OrLater:
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
    else:
        projection_matrix = camera.calc_matrix_camera(
            render.resolution_x,
            render.resolution_y,
            render.pixel_aspect_x,
            render.pixel_aspect_y)

    mp_matrix = matmul(projection_matrix, modelview_matrix)
    mpinv_matrix = mp_matrix.copy()
    mpinv_matrix.invert()

    isOrtho = bpy.context.scene.camera.data.type == 'ORTHO'

    # Convert 3d points to camera space, calculating the min and max extents in 2d normalised camera space.
    minDistToCamera = sys.float_info.max
    for point in globalPoints:
        p1 = matvecmul(mp_matrix, mathutils.Vector((point.x, point.y, point.z, 1)))
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
        centre3d = matvecmul(mpinv_matrix, mathutils.Vector((centre2d.x, centre2d.y, 0, 1)))
        centre3d = mathutils.Vector((centre3d.x, centre3d.y, centre3d.z))

        # Move centre3d a distance d from the camera plane
        v = centre3d - camera.location
        dist = v.dot(forwards3d)
        centre3d = centre3d + (d - dist) * forwards3d
    else:
        centre3d = matvecmul(mpinv_matrix, mathutils.Vector((centre2d.x, centre2d.y, -1, 1)))
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
def loadFromFile(context, filename, isFullFilepath=True):
    global globalCamerasToAdd
    global globalContext

    globalCamerasToAdd = []
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
    CachedDirectoryFilenames.clearCache()
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
    node = LDrawNode(filename, isFullFilepath, os.path.dirname(filename))
    node.load()
    # node.printBFC()

    # Fix top level rotation from LDraw coordinate space to Blender coordinate space
    node.file.geometry.points = list(map((lambda p: matvecmul(Math.rotationMatrix, p)), node.file.geometry.points))
    node.file.geometry.edges  = list(map((lambda e: (matvecmul(Math.rotationMatrix, e[0]), matvecmul(Math.rotationMatrix, e[1]))), node.file.geometry.edges))
    for childNode in node.file.childNodes:
        childNode.matrix = matmul(Math.rotationMatrix, childNode.matrix)

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
    rootOb = createBlenderObjectsFromNode(node, node.matrix, name)

    scene  = bpy.context.scene
    camera = scene.camera
    render = scene.render

    debugPrint("Number of vertices: " + str(len(globalPoints)))

    # Take the convex hull of all the points in the scene (operation must have at least three vertices)
    # This results in far fewer points to consider when adjusting the object and/or camera position.
    if len(globalPoints) >= 3:
        bm = bmesh.new()
        [bm.verts.new(v) for v in globalPoints]
        bm.verts.ensure_lookup_table()

        ret = bmesh.ops.convex_hull(bm, input=bm.verts, use_existing_faces=False)
        globalPoints = [vert.co.copy() for vert in ret["geom"] if isinstance(vert, bmesh.types.BMVert)]
        del ret
        bm.clear()
        bm.free()

        debugPrint("Number of vertices of convex hull: " + str(len(globalPoints)))

        # Put convex hull back into scene - for testing purposes
        # mesh_dst = bpy.data.meshes.new(name="convexHull")
        # bm.to_mesh(mesh_dst)
        # obj_cell = bpy.data.objects.new(name="convexHull", object_data=mesh_dst)
        # linkToScene(obj_cell)

    # Centre object
    if globalPoints:
        # Calculate our bounding box in global coordinate space
        boundingBoxMin = mathutils.Vector((0, 0, 0))
        boundingBoxMax = mathutils.Vector((0, 0, 0))

        boundingBoxMin[0] = min(p[0] for p in globalPoints)
        boundingBoxMin[1] = min(p[1] for p in globalPoints)
        boundingBoxMin[2] = min(p[2] for p in globalPoints)
        boundingBoxMax[0] = max(p[0] for p in globalPoints)
        boundingBoxMax[1] = max(p[1] for p in globalPoints)
        boundingBoxMax[2] = max(p[2] for p in globalPoints)

        vcentre = (boundingBoxMin + boundingBoxMax) * 0.5
        offsetToCentreModel = mathutils.Vector((-vcentre.x, -vcentre.y, -boundingBoxMin.z))
        if Options.positionObjectOnGroundAtOrigin:
            debugPrint("Centre object")
            rootOb.location += offsetToCentreModel
            
            # Offset all points
            globalPoints = [p + offsetToCentreModel for p in globalPoints]
            offsetToCentreModel = mathutils.Vector((0, 0, 0))

    if camera is not None:
        if Options.positionCamera:
            debugPrint("Positioning Camera")
    
            # Set up a default camera position and rotation
            camera.location = mathutils.Vector((6.5, -6.5, 4.75))
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

    # Get existing scene names
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

    # Add cameras to the scene
    for ob in globalCamerasToAdd:
        cam = ob.createCameraNode()
        cam.parent = rootOb

    globalObjectsToAdd = []
    globalCamerasToAdd = []

    # Select the newly created root object
    selectObject(rootOb)

    # Get existing scene names
    sceneObjectNames = [x.name for x in scene.objects]

    # Add ground plane with white material
    if Options.addGroundPlane and not Options.instructionsLook:
        if "LegoGroundPlane" not in sceneObjectNames:
            addPlane((0,0,0), 100000 * Options.scale)

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

    debugPrint("Load Done")
    return rootOb
