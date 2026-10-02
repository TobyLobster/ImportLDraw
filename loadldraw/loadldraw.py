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
import textwrap
import base64
import binascii
import hashlib

from pprint import pprint

# **************************************************************************************
def getImportCollection():
    """The collection that imported objects are added to"""
    collection = bpy.context.collection
    scene = bpy.context.scene
    if collection == scene.collection:
        # Objects linked directly to the scene's master collection can't be excluded from a
        # view layer, and the instructions look relies on excluding them (solid and transparent
        # bricks are rendered in separate view layers). So we use a child collection instead.
        name = "LDraw Models"
        collection = bpy.data.collections.get(name)
        if collection is None:
            collection = bpy.data.collections.new(name)
        if scene.collection.children.find(collection.name) < 0:
            scene.collection.children.link(collection)
    return collection

# **************************************************************************************
def linkToScene(ob):
    collection = getImportCollection()
    if collection.objects.find(ob.name) < 0:
        collection.objects.link(ob)

# **************************************************************************************
def linkToCollection(collectionName, ob):
    # Add object to the appropriate collection
    if bpy.data.collections[collectionName].objects.find(ob.name) < 0:
        bpy.data.collections[collectionName].objects.link(ob)

# **************************************************************************************
def unlinkFromScene(ob):
    for collection in (getImportCollection(), bpy.context.collection):
        if collection.objects.find(ob.name) >= 0:
            collection.objects.unlink(ob)

# **************************************************************************************
def selectObject(ob):
    ob.select_set(state=True)
    bpy.context.view_layer.objects.active = ob

# **************************************************************************************
def deselectObject(ob):
    ob.select_set(state=False)
    bpy.context.view_layer.objects.active = None

# **************************************************************************************
def addPlane(location, size, name):
    """Adds a square plane to the current collection, without using an operator (which would update the whole scene)"""
    half = size * 0.5
    mesh = bpy.data.meshes.new("Plane")
    mesh.from_pydata([(-half, -half, 0), (half, -half, 0), (-half, half, 0), (half, half, 0)], [], [(0, 1, 3, 2)])
    uvs = mesh.uv_layers.new(name="UVMap")
    for loop, uv in zip(uvs.data, ((0, 0), (1, 0), (1, 1), (0, 1))):
        loop.uv = uv
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    ob.location = location
    bpy.context.collection.objects.link(ob)
    return ob

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
    """Shows a message in a popup (wrapped over several lines). Does nothing when there is no window, e.g. in background mode."""
    if bpy.app.background or bpy.context.window_manager is None or bpy.context.window is None:
        return

    lines = textwrap.wrap(message, 90) or [""]

    def draw(self, context):
        for line in lines:
            self.layout.label(text=line)

    try:
        bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)
    except RuntimeError:
        pass


# **************************************************************************************
# **************************************************************************************
MESH_FORMAT_VERSION = 3     # 2 = texture coordinates and print normals (version 1.3.0)
                            # 3 = sharp edges found along edge lines that span several mesh edges, T-junctions
                            #     joined up, and a bevel weight for each edge so its bevel can't overlap (issue #29)

class Options:
    """User Options"""

    # Full filepath to ldraw folder. If empty, some standard locations are attempted
    ldrawDirectory     = r""            # Full filepath to the ldraw parts library (searches some standard locations if left blank)
    instructionsLook   = False          # Set up scene to look like Lego Instruction booklets
    #scale              = 0.01           # Size of the lego model to create. (0.04 is LeoCAD scale)
    realScale          = 1              # Scale of lego model to create (1 represents real Lego scale)
    useUnofficialParts = True           # Additionally searches <ldraw-dir>/unofficial/parts and /p for files
    resolution         = "Standard"     # Choose from "High", "Standard", or "Low"
    defaultColour      = "4"            # Default colour ("4" = red)
    createInstances    = True           # Multiple bricks share geometry (recommended)
    useColourScheme    = "lgeo"         # "ldraw", "alt", or "lgeo". LGEO gives the most true-to-life colours.
    numberNodes        = True           # Each node's name has a numerical prefix eg. 00001_car.dat (keeps nodes listed in a fixed order)
    removeDoubles      = True           # Remove duplicate vertices (recommended)
    joinTJunctions     = True           # Join faces that meet along an edge at different vertices (a 'T-junction'), so the mesh is closed there and can be bevelled (needs removeDoubles)
    smoothShading      = True           # Smooth the surface normals (recommended)
    edgeSplit          = True           # Edge split modifier (recommended if you use smoothShading)
    gaps               = True           # Introduces a tiny space between each brick
    realGapWidth       = 0.0001         # Width of gap between bricks (in metres)
    curvedWalls        = True           # Manipulate normals to make surfaces look slightly concave
    importCameras      = True           # LeoCAD can specify cameras within the ldraw file format. Choose to load them or ignore them.
    positionObjectOnGroundAtOrigin = True   # Centre the object at the origin, sitting on the z=0 plane
    flattenHierarchy   = False          # All parts are under the root object - no sub-models
    submodelCollections = False         # Each submodel (and the model itself) also gets its own collection, nested like the submodels
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
    useTextures = True                  # Apply !TEXMAP textures (otherwise the untextured FALLBACK geometry is used)
    packEmbeddedImages = True           # Images embedded in a model ('0 !DATA') are packed into the .blend file (otherwise written next to the model)
    sharpTextureMaxSize = 64            # Texture images this size or smaller (in pixels, longest side) are drawn pixel sharp rather than smoothed
    instructionsTransparentOpacity = 0.95    # Instructions look: opacity of transparent parts (0 = invisible, 1 = opaque) before the compositor's Set Alpha (0.75)

    def meshOptionsString():
        """These options change the mesh, so if they change, a new mesh needs to be cached"""

        # MESH_FORMAT_VERSION changes when the importer starts building meshes differently (e.g. with
        # texture coordinates), so meshes made by an earlier version of the add-on aren't reused.
        return "_".join([str(MESH_FORMAT_VERSION),
                         str(Options.realScale),
                         str(Options.useUnofficialParts),
                         str(Options.instructionsLook),
                         str(Options.resolution),
                         str(Options.defaultColour),
                         str(Options.createInstances),
                         str(Options.useColourScheme),
                         str(Options.removeDoubles),
                         str(Options.joinTJunctions),
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
                         str(Options.useTextures),
                         str(Options.bevelWidth)])

# **************************************************************************************
# Globals
globalBrickCount = 0
globalObjectsToAdd = []         # Blender objects to add to the scene
globalMissingFiles = []         # Files referenced by the import that could not be found
globalCamerasToAdd = []         # Camera data to add to the scene
globalGroupObjects = {}         # LeoCAD group empties created this import, keyed by (parent object, group name)
globalCurrentCollection = None  # With Options.submodelCollections: the collection for objects being created now
globalHiddenObjects = []        # Objects of pieces LeoCAD marked as hidden (hidden once they are in the scene)
globalObjectParts = {}          # Object pointer -> (bare part number, category) of the objects created this import (for minifig rigging)
globalObjectCollections = {}    # With Options.submodelCollections: object pointer -> the collection it belongs in
globalImportFilepath = ""       # The file being imported (embedded images may be written next to it)

PRINT_NORMAL_ATTRIBUTE = "ldraw_print_normal"   # Face corner attribute: the normal of the textured face each corner belongs to
PRINT_NORMAL_TOLERANCE_DEGREES = 2.0            # Textured faces are flat to within 1 degree; bevel strips turn by far more
globalContext = None
globalPoints = []
globalScaleFactor = 0.0004
globalWeldDistance = 0.0005

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
    else:
        # Called from a script (no operator to report to), so show it in a popup instead
        ShowMessageBox(message, "Import LDraw", 'CANCEL')


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
    studMinimalTranslationMatrix = mathutils.Matrix.Translation((0.0, -0.0001, 0))

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

    localSearchPaths = []
    officialSearchPaths = []
    unofficialSearchPaths = []
    warningSuppression = {}
    tempDir = None
    unofficialDirectory = ""        # The unofficial parts: a folder (usually '<ldraw>/unofficial') or 'ldrawunf.zip'

    def appendLocalPath(path):
        path = FileSystem.pathInsensitive(path)
        if FileSystem.exists(path):
            Configure.localSearchPaths.append(path)

    def appendOfficialPath(path):
        path = FileSystem.pathInsensitive(path)
        if FileSystem.exists(path):
            Configure.officialSearchPaths.append(path)

    def appendUnofficialPath(path):
        path = FileSystem.pathInsensitive(path)
        if FileSystem.exists(path):
            Configure.unofficialSearchPaths.append(path)

    def __setSearchPaths():
        Configure.localSearchPaths = []
        Configure.officialSearchPaths = []
        Configure.unofficialSearchPaths = []

        # Always search for parts in the 'models' folder
        Configure.appendOfficialPath(os.path.join(Configure.ldrawInstallDirectory, "models"))

        # Search for stud logo parts first since we want our local stud files to take priority
        # (Our local studs include versions with the 'LEGO' logo)
        if Options.useLogoStuds and Options.studLogoDirectory != "":
            if Options.resolution == "Low":
                Configure.appendLocalPath(os.path.join(Options.studLogoDirectory, "8"))
            Configure.appendLocalPath(Options.studLogoDirectory)

        # Search official parts
        if Options.resolution == "High":
            Configure.appendOfficialPath(os.path.join(Configure.ldrawInstallDirectory, "p", "48"))
            debugPrint("High-res primitives selected")
        elif Options.resolution == "Low":
            Configure.appendOfficialPath(os.path.join(Configure.ldrawInstallDirectory, "p", "8"))
            debugPrint("Low-res primitives selected")
        else:
            debugPrint("Standard-res primitives selected")

        Configure.appendOfficialPath(os.path.join(Configure.ldrawInstallDirectory, "p"))
        Configure.appendOfficialPath(os.path.join(Configure.ldrawInstallDirectory, "parts"))

        # Search unofficial parts
        if Options.useUnofficialParts:
            if Options.resolution == "High":
                Configure.appendUnofficialPath(os.path.join(Configure.unofficialDirectory, "p", "48"))
            elif Options.resolution == "Low":
                Configure.appendUnofficialPath(os.path.join(Configure.unofficialDirectory, "p", "8"))
            Configure.appendUnofficialPath(os.path.join(Configure.unofficialDirectory, "p"))
            Configure.appendUnofficialPath(os.path.join(Configure.unofficialDirectory, "parts"))

        # Search LSynth parts
        if Options.useLSynthParts:
            if Options.LSynthDirectory != "":
                Configure.appendOfficialPath(Options.LSynthDirectory)
            elif Options.useUnofficialParts:
                Configure.appendUnofficialPath(os.path.join(Configure.ldrawInstallDirectory, "unofficial", "lsynth"))
            debugPrint("Use LSynth Parts requested")

        # Last resort, try the Tente parts
        if Options.useUnofficialParts:
            # Add 'Tente' parts too
            if Options.resolution == "High":
                Configure.appendUnofficialPath(os.path.join(Configure.ldrawInstallDirectory, "tente", "p", "48"))
            elif Options.resolution == "Low":
                Configure.appendUnofficialPath(os.path.join(Configure.ldrawInstallDirectory, "tente", "p", "8"))
            Configure.appendUnofficialPath(os.path.join(Configure.ldrawInstallDirectory, "tente", "p"))
            Configure.appendUnofficialPath(os.path.join(Configure.ldrawInstallDirectory, "tente", "parts"))

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

        # Search possible directories (an unzipped library, or a folder with the zipped library in it)
        for dir in ldrawPossibleDirectories:
            dir = FileSystem.pathInsensitive(os.path.expanduser(dir))
            if os.path.isfile(FileSystem.pathInsensitive(os.path.join(dir, "LDConfig.ldr"))):
                result = dir
                break
            if os.path.isfile(FileSystem.pathInsensitive(os.path.join(dir, "complete.zip"))):
                result = dir
                break

        return result

    def __findZipLibraries(directory):
        """
        The parts library can also be used still zipped, as downloaded from ldraw.org:
        'directory' can be the 'complete.zip' file itself, or a folder containing it (when the folder
        doesn't have an unzipped library in it). Returns the library directory to use.
        """
        if directory.lower().endswith(".zip"):
            # Opening the zip indexes it, so the paths inside it are recognised from now on
            if not ZipLibrary.isLibrary(directory):
                message = "Could not read the LDraw parts library zip file '{0}'".format(directory)
                if message not in Configure.warningSuppression:
                    Configure.warningSuppression[message] = True
                    printError(message)
            return directory

        if not os.path.isfile(FileSystem.pathInsensitive(os.path.join(directory, "LDConfig.ldr"))):
            zipPath = FileSystem.pathInsensitive(os.path.join(directory, "complete.zip"))
            if os.path.isfile(zipPath) and ZipLibrary.isLibrary(zipPath):
                return zipPath
        return directory

    def __findUnofficialDirectory():
        """
        The unofficial parts: an 'unofficial' folder in the library, or failing that the zipped
        'ldrawunf.zip' from ldraw.org, in the library folder or next to 'complete.zip'.
        """
        folder = FileSystem.pathInsensitive(os.path.join(Configure.ldrawInstallDirectory, "unofficial"))
        if FileSystem.exists(folder):
            return folder

        if ZipLibrary.contains(Configure.ldrawInstallDirectory):
            places = [os.path.dirname(Configure.ldrawInstallDirectory)]
        else:
            places = [Configure.ldrawInstallDirectory, folder]
        for place in places:
            zipPath = FileSystem.pathInsensitive(os.path.join(place, "ldrawunf.zip"))
            if os.path.isfile(zipPath) and ZipLibrary.isLibrary(zipPath):
                return zipPath
        return folder

    def setLDrawDirectory():
        if Options.ldrawDirectory == "":
            Configure.ldrawInstallDirectory = Configure.findDefaultLDrawDirectory()
        else:
            Configure.ldrawInstallDirectory = os.path.expanduser(Options.ldrawDirectory)

        if Configure.ldrawInstallDirectory != "":
            Configure.ldrawInstallDirectory = Configure.__findZipLibraries(Configure.ldrawInstallDirectory)
            Configure.unofficialDirectory = Configure.__findUnofficialDirectory()

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

    # Colours used if they are missing from both LDConfig.ldr and Stud.io's colour table.
    # (code: (name, sRGB hex, alpha))
    __fallbackColours = {
        10375:  ("Trans_Black", "212121", 128 / 256.0),     # Added to LDConfig.ldr in 2024 (code 40 became Trans_Brown)
        100040: ("Trans_Black", "5E5E5C", 128 / 256.0),     # Stud.io's code for Trans-Black
    }

    def __addColour(code, name, hexDigits, alpha, material="BASIC"):
        linearRGBA = LegoColours.hexDigitsToLinearRGBA(hexDigits, alpha)
        LegoColours.colours[code] = {
            "name": name,
            "colour": linearRGBA[0:3],
            "alpha": alpha,
            "luminance": 0.0,
            "material": material
        }

    def __findStudioColourTable():
        """Returns the path of Stud.io's colour table (StudioColorDefinition.txt) if found, else None."""
        candidates = []
        if Configure.ldrawInstallDirectory:
            # Stud.io's own LDraw library is at 'Studio 2.0/ldraw', and its data folder is 'Studio 2.0/data'
            studioDir = os.path.dirname(os.path.normpath(Configure.ldrawInstallDirectory))
            candidates.append(os.path.join(studioDir, "data", "StudioColorDefinition.txt"))
        if Configure.isMac():
            candidates.append("/Applications/Studio 2.0/data/StudioColorDefinition.txt")
        elif Configure.isWindows():
            candidates.append("C:\\Program Files\\Studio 2.0\\data\\StudioColorDefinition.txt")
            candidates.append("C:\\Program Files (x86)\\Studio 2.0\\data\\StudioColorDefinition.txt")
        for candidate in candidates:
            candidate = FileSystem.pathInsensitive(candidate)
            if os.path.isfile(candidate):
                return candidate
        return None

    def __readStudioColourTable():
        """Adds colours from Stud.io's colour table that are missing from LDConfig.ldr.
        Stud.io uses some colour codes of its own (e.g. 100040 for Trans-Black), and its copy
        of LDConfig.ldr can be very old."""
        filepath = LegoColours.__findStudioColourTable()
        if filepath is None:
            return

        materials = {
            "Chrome Colors":   "CHROME",
            "Pearl Colors":    "PEARLESCENT",
            "Metallic Colors": "METAL",
            "Rubber Colors":   "RUBBER",
        }

        try:
            with open(filepath, "rt", encoding="utf_8_sig", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return

        # Tab separated columns: Studio Color Code, BL Color Code, LDraw Color Code, LDD color code,
        # Studio Color Name, BL Color Name, LDraw Color Name, LDD Color Name, RGB value, Alpha, CategoryName, ...
        for line in lines[1:]:
            columns = line.rstrip("\r\n").split("\t")
            if len(columns) < 11:
                continue
            try:
                code = int(columns[2])
                hexDigits = columns[8].strip().lstrip("#")
                alpha = float(columns[9])
            except ValueError:
                continue
            if code in LegoColours.colours or len(hexDigits) != 6:
                continue
            name = (columns[6].strip() or columns[4].strip()).replace(" ", "_")
            try:
                LegoColours.__addColour(code, name, hexDigits, alpha, materials.get(columns[10].strip(), "BASIC"))
            except ValueError:
                continue

    def __readColourTable():
        """Reads the colour values from the LDConfig.ldr file. For details of the
        Ldraw colour system see: http://www.ldraw.org/article/547"""
        LegoColours.colours = {}

        if Options.useColourScheme == "alt":
            configFilename = "LDCfgalt.ldr"
        else:
            configFilename = "LDConfig.ldr"

        configFilepath = FileSystem.pathInsensitive(os.path.join(Configure.ldrawInstallDirectory, configFilename))

        ldconfig_lines = ""
        if FileSystem.exists(configFilepath):
            ldconfig_lines = FileSystem.readTextFile(configFilepath) or ""

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

                        # current `FABRIC [VELVET | CANVAS | STRING | FUR]` is not yet supported.
                        if colour["material"] == "FABRIC":
                            debugPrint(f"Unsupported material finish: {colour['material']} for [colour: {name} code: {code}] in line: {subline}")

                        # Note, not all finishes have a secondary value
                        finishValue                    = LegoColours.__getValue(subline, "VALUE")
                        if finishValue is not None:
                            hexDigits                  = finishValue[1:]
                            colour["secondary_colour"] = LegoColours.hexDigitsToLinearRGBA(hexDigits, 1.0)

                        colour["fraction"]         = LegoColours.__getValue(subline, "FRACTION")
                        colour["vfraction"]        = LegoColours.__getValue(subline, "VFRACTION")
                        colour["size"]             = LegoColours.__getValue(subline, "SIZE")
                        colour["minsize"]          = LegoColours.__getValue(subline, "MINSIZE")
                        colour["maxsize"]          = LegoColours.__getValue(subline, "MAXSIZE")

                    LegoColours.colours[code] = colour

        # Add any colours that LDConfig.ldr doesn't define (e.g. if it is out of date)
        LegoColours.__readStudioColourTable()
        for code, (name, hexDigits, alpha) in LegoColours.__fallbackColours.items():
            if code not in LegoColours.colours:
                LegoColours.__addColour(code, name, hexDigits, alpha)

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
class ZipLibrary:
    """
    An LDraw parts library read straight from its zip file, without unzipping it: the official
    'complete.zip' (whose files are in an 'ldraw' folder) or the unofficial 'ldrawunf.zip' (whose
    'parts' and 'p' folders are at the top level).

    The zip file's path is treated like a folder: the file 'ldraw/parts/3001.dat' in
    '/x/complete.zip' has the path '/x/complete.zip/parts/3001.dat'. So the rest of the importer
    can use these paths like any others, through FileSystem.
    """

    __archives = {}     # zip filepath -> archive details (see __open)

    def __open(zipPath):
        """Opens and indexes a zip file, or returns the details from last time if it is unchanged"""
        try:
            stat = os.stat(zipPath)
        except OSError:
            return None
        stamp = (stat.st_mtime, stat.st_size)
        archive = ZipLibrary.__archives.get(zipPath)
        if archive is not None and archive["stamp"] == stamp:
            return archive

        try:
            zipFile = zipfile.ZipFile(zipPath)
            names = zipFile.namelist()
        except (OSError, zipfile.BadZipFile):
            return None

        # Use the 'ldraw' folder as the top of the library, if there is one
        prefix = ""
        lowerNames = [name.lower() for name in names]
        if "ldraw/ldconfig.ldr" in lowerNames or any(name.startswith("ldraw/parts/") for name in lowerNames):
            prefix = "ldraw/"

        files = {}          # lowercase path in the library -> name in the zip
        folders = set()     # lowercase paths of folders in the library
        for name, lowerName in zip(names, lowerNames):
            if name.endswith("/") or not lowerName.startswith(prefix):
                continue
            relative = lowerName[len(prefix):]
            files[relative] = name
            parts = relative.split("/")
            for i in range(1, len(parts)):
                folders.add("/".join(parts[:i]))

        archive = {"stamp": stamp, "zip": zipFile, "prefix": prefix, "files": files, "folders": folders}
        ZipLibrary.__archives[zipPath] = archive
        debugPrint("Opened parts library {0} ({1} files)".format(zipPath, len(files)))
        return archive

    def isLibrary(zipPath):
        """Is this a zip file we can read a parts library from?"""
        return zipPath.lower().endswith(".zip") and os.path.isfile(zipPath) and ZipLibrary.__open(zipPath) is not None

    def __find(path):
        """Splits a path into (archive, zip filepath, lowercase path inside the library), or None if it isn't in an opened zip"""
        for zipPath in ZipLibrary.__archives:
            if path == zipPath:
                return (ZipLibrary.__archives[zipPath], zipPath, "")
            if path.startswith(zipPath) and path[len(zipPath)] in ("/", "\\"):
                inner = path[len(zipPath) + 1:].replace("\\", "/").lower()
                inner = "/".join(part for part in inner.split("/") if part not in ("", "."))
                return (ZipLibrary.__archives[zipPath], zipPath, inner)
        return None

    def contains(path):
        return ZipLibrary.__find(path) is not None

    def exists(path):
        found = ZipLibrary.__find(path)
        if found is None:
            return False
        archive, zipPath, inner = found
        return inner == "" or inner in archive["files"] or inner in archive["folders"]

    def isFile(path):
        found = ZipLibrary.__find(path)
        return found is not None and found[2] in found[0]["files"]

    def canonical(path):
        """The path with the capitalisation used in the zip file (or unchanged if it isn't there)"""
        found = ZipLibrary.__find(path)
        if found is None:
            return path
        archive, zipPath, inner = found
        name = archive["files"].get(inner)
        if name is None:
            return path
        return os.path.join(zipPath, *name[len(archive["prefix"]):].split("/"))

    def read(path):
        """The bytes of a file in a zip, or None"""
        found = ZipLibrary.__find(path)
        if found is None:
            return None
        archive, zipPath, inner = found
        name = archive["files"].get(inner)
        if name is None:
            return None
        try:
            return archive["zip"].read(name)
        except (OSError, zipfile.BadZipFile, KeyError):
            return None


# **************************************************************************************
# **************************************************************************************
class FileSystem:
    """
    Reads text files in different encodings. Locates full filepath for a part.
    Files can be in a folder or in a zipped parts library (see ZipLibrary).
    """

    def exists(path):
        """Does the file or folder exist (on disk or in a zipped parts library)?"""
        if ZipLibrary.contains(path):
            return ZipLibrary.exists(path)
        return os.path.exists(path)

    def isFile(path):
        if ZipLibrary.contains(path):
            return ZipLibrary.isFile(path)
        return os.path.isfile(path)

    def readBytes(path):
        if ZipLibrary.contains(path):
            return ZipLibrary.read(path)
        try:
            with open(path, "rb") as file:
                return file.read()
        except OSError:
            return None

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

        if ZipLibrary.contains(path):
            return ZipLibrary.canonical(path)
        return FileSystem.__pathInsensitive(path) or path

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

        if ZipLibrary.contains(filepath):
            data = ZipLibrary.read(filepath)
            if data is None:
                return None
            if data.startswith(b"\xfe\xff\x00"):
                encoding = "utf_16_be"
            elif data.startswith(b"\xff\xfe0"):
                encoding = "utf_16_le"
            else:
                encoding = "utf_8"
            try:
                text = data.decode(encoding)
            except UnicodeDecodeError:
                text = data.decode("latin_1")
            # As reading a file in text mode would: universal newlines, keeping the line endings
            return text.replace("\r\n", "\n").replace("\r", "\n").splitlines(True)

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

        # Gather all paths in the order we want to search
        allSearchPaths = []
        allSearchPaths.extend(Configure.localSearchPaths)
        allSearchPaths.extend(Configure.unofficialSearchPaths)
        allSearchPaths.extend(Configure.officialSearchPaths)
        if rootPath not in allSearchPaths:
            allSearchPaths.append(rootPath)

        for path in allSearchPaths:
            fullPathName = os.path.join(path, partName)
            fullPathName = FileSystem.pathInsensitive(fullPathName)

            if FileSystem.exists(fullPathName):
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
class EmbeddedImages:
    """
    Images embedded in LDraw files in '0 !DATA <name>' sections, as base64 in '0 !:' lines.
    See https://www.ldraw.org/article/47.html
    An embedded image is used in preference to a file of the same name.
    """

    __images = {}       # Normalised name -> (bytes, filepath of the file it was embedded in)

    def __normalise(name):
        return name.strip().replace("\\", "/").lower()

    def addSection(name, lines, sourceFilepath):
        """Decodes a '0 !DATA' section (including its '0 !DATA' line)"""
        chunks = []
        for line in lines:
            parameters = line.split(None, 2)
            if len(parameters) >= 2 and parameters[0] == "0" and parameters[1] == "!:":
                if len(parameters) > 2:
                    chunks.append(parameters[2])
        text = "".join("".join(chunks).split())
        # Accept the URL safe alphabet too, and missing padding
        text = text.replace("-", "+").replace("_", "/")
        text += "=" * (-len(text) % 4)
        try:
            data = base64.b64decode(text)
        except (binascii.Error, ValueError):
            printWarningOnce("Could not decode the embedded image '{0}' in {1}".format(name, sourceFilepath))
            return
        if not data:
            printWarningOnce("The embedded image '{0}' in {1} is empty".format(name, sourceFilepath))
            return

        # The first one found wins (the importing file is read before the files it uses)
        EmbeddedImages.__images.setdefault(EmbeddedImages.__normalise(name), (data, sourceFilepath))

    def get(name):
        """Returns (bytes, sourceFilepath) for an embedded image, or None"""
        key = EmbeddedImages.__normalise(name)
        result = EmbeddedImages.__images.get(key)
        if result is None:
            if key.startswith("textures/"):
                result = EmbeddedImages.__images.get(key[len("textures/"):])
            else:
                result = EmbeddedImages.__images.get("textures/" + key)
        return result

    def clearCache():
        EmbeddedImages.__images = {}

# **************************************************************************************
# **************************************************************************************
class FaceInfo:
    def __init__(self, faceColour, culling, windingCCW, isGrainySlopeAllowed, texmap=None, uvs=None):
        self.faceColour = faceColour
        self.culling = culling
        self.windingCCW = windingCCW
        self.isGrainySlopeAllowed = isGrainySlopeAllowed
        self.texmap = texmap            # TexMap applied to this face, or None
        self.uvs = uvs                  # One (u, v) per corner of the face when textured


# **************************************************************************************
# **************************************************************************************
class TexMap:
    """
    A texture mapping, from a '0 !TEXMAP START' or '0 !TEXMAP NEXT' line.
    See https://www.ldraw.org/texmap-spec.html

    The points are in the coordinates of the file that declares the texture (scaled
    to Blender units, like the geometry).
    """

    __parameterCounts = {"PLANAR": 9, "CYLINDRICAL": 10, "SPHERICAL": 11}
    __supportedMethods = ("PLANAR", "CYLINDRICAL", "SPHERICAL")

    def __init__(self, method, numbers, imageName, glossmapName, declaringFilepath):
        self.method = method
        self.imageName = imageName
        self.glossmapName = glossmapName            # Parsed but not used yet
        self.declaringFilepath = declaringFilepath
        self.supported = (method in TexMap.__supportedMethods) and (imageName != "")
        self.localToTex = None          # Matrix from the coordinates the texture is used in to those it was declared in (None = the same)
        self.wrapU = False              # The image goes all the way round (360 degrees), so U wraps around
        self.points = []
        self.angles = []
        if not self.supported:
            return

        self.points = [Math.scaleMatrix @ mathutils.Vector(numbers[i:i + 3]) for i in (0, 3, 6)]
        self.angles = [math.radians(a) for a in numbers[9:]]
        p1, p2, p3 = self.points

        if method == "PLANAR":
            # p1 = top left of the image, p2 = top right, p3 = bottom left
            self.uAxis = p2 - p1
            self.vAxis = p3 - p1
            self.uLengthSquared = self.uAxis.length_squared
            self.vLengthSquared = self.vAxis.length_squared
            if self.uLengthSquared == 0.0 or self.vLengthSquared == 0.0:
                self.supported = False

        elif method == "CYLINDRICAL":
            # p1 = centre of the bottom, p2 = centre of the top, p3 = a point on the bottom edge where
            # the bottom centre of the image touches. The image covers angle a around the axis.
            self.centre = p2
            axis = p2 - p1
            self.height = axis.length
            self.normal = axis / self.height if self.height > 0.0 else None
            self.direction = self.__radial(p3) if self.normal is not None else None
            if self.direction is None or self.angles[0] == 0.0:
                self.supported = False
            else:
                self.wrapU = abs(self.angles[0]) >= 2.0 * math.pi - 1e-6

        elif method == "SPHERICAL":
            # p1 = centre, p2 = where the centre of the image touches the sphere, p3 = a third point
            # that with p1 and p2 makes the plane that cuts the image in half horizontally. The image
            # covers angle a around the sphere and angle b from pole to pole.
            self.centre = p1
            normal = -((p1 - p2).cross(p3 - p2))
            toImageCentre = p2 - p1
            if normal.length == 0.0 or toImageCentre.length == 0.0 or self.angles[0] == 0.0 or self.angles[1] == 0.0:
                self.supported = False
            else:
                self.normal = normal.normalized()                   # Towards the top of the image
                self.direction = toImageCentre.normalized()
                self.wrapU = abs(self.angles[0]) >= 2.0 * math.pi - 1e-6

    def __radial(self, point):
        """The unit direction from the axis (through self.centre, along self.normal) to the point, or None if on the axis"""
        d = point - self.centre
        radial = d - d.dot(self.normal) * self.normal
        if radial.length <= 1e-6 * max(d.length, 1e-12):
            return None
        return radial.normalized()

    def __angles(self, points):
        """
        The angle around the axis of each point, measured from the image centre line, going
        anticlockwise when seen from the top. Within one face the angles are kept continuous
        (not jumping from +180 to -180 degrees), so a face that crosses the join at the back
        maps onto a continuous range of the image. Points on the axis get None.
        """
        result = []
        baseDirection = None
        baseAngle = 0.0
        for point in points:
            radial = self.__radial(point)
            if radial is None:
                result.append(None)
            elif baseDirection is None:
                baseDirection = radial
                baseAngle = math.atan2(self.direction.cross(radial).dot(self.normal), radial.dot(self.direction))
                result.append(baseAngle)
            else:
                result.append(baseAngle + math.atan2(baseDirection.cross(radial).dot(self.normal), radial.dot(baseDirection)))
        # A point on the axis (a pole) takes the average angle of the others
        known = [angle for angle in result if angle is not None]
        average = sum(known) / len(known) if known else 0.0
        return [average if angle is None else angle for angle in result]

    def parse(parameters, declaringFilepath):
        """Parses the parameters that follow 'START' or 'NEXT'. Always returns a TexMap (check 'supported')."""
        parameters = [p for p in parameters if p != ""]
        if not parameters:
            return TexMap("", [], "", "", declaringFilepath)

        method = parameters[0].upper()
        count = TexMap.__parameterCounts.get(method)
        if count is None or len(parameters) < 2 + count:
            printWarningOnce("Unknown !TEXMAP method '{0}' in {1}".format(method, declaringFilepath))
            return TexMap(method, [], "", "", declaringFilepath)

        try:
            numbers = [float(x) for x in parameters[1:1 + count]]
        except ValueError:
            printWarningOnce("Bad !TEXMAP parameters in {0}".format(declaringFilepath))
            return TexMap(method, [], "", "", declaringFilepath)

        # The image name may contain spaces; an optional 'GLOSSMAP <name>' follows it
        rest = parameters[1 + count:]
        glossmapName = ""
        if "GLOSSMAP" in rest:
            index = rest.index("GLOSSMAP")
            glossmapName = " ".join(rest[index + 1:])
            rest = rest[:index]
        imageName = " ".join(rest)

        return TexMap(method, numbers, imageName, glossmapName, declaringFilepath)

    def transformed(self, matrix):
        """
        The same texture, for use in the coordinates of a subfile placed with 'matrix'
        (which maps the subfile's coordinates to our current ones).
        """
        result = copy.copy(self)
        result.localToTex = matrix.copy() if self.localToTex is None else self.localToTex @ matrix
        return result

    def signature(self):
        """
        A short string that is the same for textures that give the same texture coordinates, in
        the current coordinates. Used to name and cache meshes.
        """
        localToTex = self.localToTex if self.localToTex is not None else Math.identityMatrix
        values = []
        if self.method == "PLANAR":
            # u and v are each an affine function of the point, u = a.p + b
            linear = localToTex.to_3x3().transposed()
            for axis, lengthSquared in ((self.uAxis, self.uLengthSquared), (self.vAxis, self.vLengthSquared)):
                a = (linear @ axis) / lengthSquared
                b = (localToTex.translation - self.points[0]).dot(axis) / lengthSquared
                values.extend(a)
                values.append(b)
        else:
            # The defining points, in the current coordinates, and the angles
            try:
                texToLocal = localToTex.inverted()
            except ValueError:
                texToLocal = Math.identityMatrix
                values.extend(v for row in localToTex for v in row)
            for point in self.points:
                values.extend(texToLocal @ point)
            values.extend(self.angles)
        scale = max(abs(v) for v in values) or 1.0
        text = "|".join([self.method,
                         self.imageName.lower(),
                         os.path.dirname(self.declaringFilepath or "").lower(),
                         "{0:.6g}".format(scale)] +
                        ["{0:.6f}".format(round(v / scale, 6) + 0.0) for v in values])
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]

    def uvs(self, points):
        """
        The (u, v) texture coordinates of the corners of one face, with v measured upwards as
        Blender expects (LDraw's v runs down the image from its top edge).
        The maths follows LDView's, the reference implementation.
        """
        if self.localToTex is not None:
            points = [self.localToTex @ p for p in points]

        if self.method == "PLANAR":
            result = []
            for point in points:
                d = point - self.points[0]
                u = d.dot(self.uAxis) / self.uLengthSquared
                v = d.dot(self.vAxis) / self.vLengthSquared
                result.append((u, 1.0 - v))
            return self.__offTheEdge(result)

        if self.method == "CYLINDRICAL":
            # U: angle around the axis. V: height up the axis (image top at the top of the cylinder)
            angles = self.__angles(points)
            return self.__offTheEdge([(0.5 + angle / self.angles[0],
                                       1.0 - self.normal.dot(self.centre - point) / self.height)
                                      for angle, point in zip(angles, points)])

        # SPHERICAL. U: longitude. V: latitude (image top towards 'normal')
        angles = self.__angles(points)
        result = []
        for angle, point in zip(angles, points):
            d = point - self.centre
            latitude = math.asin(max(-1.0, min(1.0, d.normalized().dot(self.normal)))) if d.length > 0.0 else 0.0
            result.append((0.5 + angle / self.angles[0], 0.5 + latitude / self.angles[1]))
        return self.__offTheEdge(result)

    def __offTheEdge(self, uvs):
        """
        A face lying exactly along an edge of the image (e.g. the end of a brick, when the image
        stops at that end) has every corner at U = 1, say. Rounding then puts parts of it just
        inside the image and parts just outside, so it flickers between the image and the part's
        colour. Move such a face clearly outside the image, so it shows the part's colour.
        """
        tolerance = 1e-4
        outside = 0.01
        for axis in (0, 1):
            if axis == 0 and self.wrapU:
                continue
            values = [uv[axis] for uv in uvs]
            for edge, moveTo in ((0.0, -outside), (1.0, 1.0 + outside)):
                if all(abs(value - edge) <= tolerance for value in values):
                    uvs = [(moveTo, uv[1]) if axis == 0 else (uv[0], moveTo) for uv in uvs]
        return uvs


# **************************************************************************************
# **************************************************************************************
class LDrawGeometry:
    """Stores the geometry for an LDrawFile"""

    def __init__(self):
        self.points = []
        self.faces = []
        self.faceInfo = []
        self.edges = []

    def parseFace(self, parameters, cull, ccw, isGrainySlopeAllowed, texmap=None):
        """Parse a face from parameters"""

        num_points = int(parameters[0])
        colourName = parameters[1]

        newPoints = []
        for i in range(num_points):
            blenderPos = Math.scaleMatrix @ mathutils.Vector( (float(parameters[i * 3 + 2]),
                                                               float(parameters[i * 3 + 3]),
                                                               float(parameters[i * 3 + 4])) )
            newPoints.append(blenderPos)

        # Fix "bowtie" quadrilaterals (see http://wiki.ldraw.org/index.php?title=LDraw_technical_restrictions#Complex_quadrilaterals)
        if num_points == 4:
            nA = (newPoints[1] - newPoints[0]).cross(newPoints[2] - newPoints[0])
            nB = (newPoints[2] - newPoints[1]).cross(newPoints[3] - newPoints[1])
            nC = (newPoints[3] - newPoints[2]).cross(newPoints[0] - newPoints[2])
            if (nA.dot(nB) < 0):
                newPoints[2], newPoints[3] = newPoints[3], newPoints[2]
            elif (nB.dot(nC) < 0):
                newPoints[2], newPoints[1] = newPoints[1], newPoints[2]

        pointCount = len(self.points)
        newFace = list(range(pointCount, pointCount + num_points))
        self.points.extend(newPoints)
        self.faces.append(newFace)
        uvs = texmap.uvs(newPoints) if texmap is not None else None
        self.faceInfo.append(FaceInfo(colourName, cull, ccw, isGrainySlopeAllowed, texmap, uvs))

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

    def appendGeometry(self, geometry, matrix, isParentAStud, isStud, isStudLogo, parentMatrix, cull, invert, texmap=None):
        combinedMatrix = parentMatrix @ matrix
        isReflected = combinedMatrix.determinant() < 0.0
        reflectStudLogo = isStudLogo and isReflected

        fixedMatrix = matrix.copy()
        if reflectStudLogo:
            fixedMatrix = matrix @ Math.reflectionMatrix
            invert = not invert

        # Move studs minimally upwards a smidge, to allow the instructions look to render the edge where the stud meets the base properly
        if isParentAStud and Options.instructionsLook:
            fixedMatrix = Math.studMinimalTranslationMatrix @ fixedMatrix

        # Append face information
        pointCount = len(self.points)
        newFaceInfo = []
        for index, face in enumerate(geometry.faces):
            # Gather points for this face (and transform points)
            newPoints = []
            for i in face:
                newPoints.append(fixedMatrix @ geometry.points[i])

            # Add clockwise and/or anticlockwise sets of points as appropriate
            newFace = face.copy()
            for i in range(len(newFace)):
                newFace[i] += pointCount

            faceInfo = geometry.faceInfo[index]
            faceCCW = faceInfo.windingCCW != invert
            faceCull = faceInfo.culling and cull

            # Textures: a texture declared deeper down (already on the face) wins. Otherwise a texture
            # active on the type 1 line that included this geometry applies. Its points are in this
            # (the including file's) coordinates, which is what newPoints are in.
            faceTexmap = faceInfo.texmap
            faceUVs = faceInfo.uvs
            if faceTexmap is None and texmap is not None:
                faceTexmap = texmap
                faceUVs = texmap.uvs(newPoints)

            # If we are going to resolve ambiguous normals by "best guess" we will let
            # Blender calculate that for us later. Just cull with arbitrary winding for now.
            if not faceCull:
                if Options.resolveAmbiguousNormals == "guess":
                    faceCull = True

            if faceCCW or not faceCull:
                self.points.extend(newPoints)
                self.faces.append(newFace)

                newFaceInfo.append(FaceInfo(faceInfo.faceColour, True, True, not isStud and faceInfo.isGrainySlopeAllowed, faceTexmap, faceUVs))
                self.verify(newFace, len(self.points))

            if not faceCull:
                newFace = newFace.copy()
                pointCount += len(newPoints)
                for i in range(len(newFace)):
                    newFace[i] += len(newPoints)

            if not faceCCW or not faceCull:
                self.points.extend(newPoints[::-1])
                self.faces.append(newFace)

                reversedUVs = faceUVs[::-1] if faceUVs is not None else None
                newFaceInfo.append(FaceInfo(faceInfo.faceColour, True, True, not isStud and faceInfo.isGrainySlopeAllowed, faceTexmap, reversedUVs))
                self.verify(newFace, len(self.points))

        self.faceInfo.extend(newFaceInfo)
        assert len(self.faces) == len(self.faceInfo)

        # Append edge information
        newEdges = []
        allowBevelWeight = not isStudLogo

        for edge in geometry.edges:
            newEdges.append( (fixedMatrix @ edge[0], fixedMatrix @ edge[1], allowBevelWeight) )
        self.edges.extend(newEdges)


# **************************************************************************************
# **************************************************************************************
class LDrawNode:
    """A node in the hierarchy. References one LDrawFile"""

    def __init__(self, filename, isFullFilepath, parentFilepath, colourName=None, matrix=Math.identityMatrix, bfcCull=True, bfcInverted=False, isLSynthPart=False, isSubPart=False, isRootNode=True, groupNames=[]):
        self.filename       = filename
        self.isFullFilepath = isFullFilepath
        self.parentFilepath = parentFilepath
        self.matrix         = matrix
        self.colourName     = colourName or Options.defaultColour
        self.bfcInverted    = bfcInverted
        self.bfcCull        = bfcCull
        self.file           = None
        self.isLSynthPart   = isLSynthPart
        self.isSubPart      = isSubPart
        self.isRootNode     = isRootNode
        self.groupNames     = groupNames.copy()
        self.texmap         = None      # Texture active on the type 1 line that references this node
        self.hidden         = False     # LeoCAD marked this piece as hidden ('0 !LEOCAD PIECE HIDDEN')

    def look_at(obj_camera, target, up_vector):
        bpy.context.view_layer.update()

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

        # Exception #2 - A subpart or primitive used directly by a model is part of the model's mesh, just as it
        #                would be part of a part's mesh. (e.g. a model that builds a printed brick from
        #                's/3005s01.dat', a brick without its front face, plus a textured front face of its own:
        #                as one mesh, the edges where they meet are bevelled together.)
        #                This matches what already happens when flattening the hierarchy.
        if self.file.isSubPartOrPrimitive:
            isBON = False

        # Exception #3 - We are not a Blender Object if we are an LSynth part (so that all LSynth parts become a single mesh)
        if self.isLSynthPart:
            isBON = False

        # Exception #4 - We are a Blender Object if we are a stud to be instanced
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

    def getBlenderGeometry(self, realColourName, basename, parentMatrix=Math.identityMatrix, accumCull=True, accumInvert=False, texmap=None):
        """
        Returns the geometry for the Blender Object at this node.

        It accumulates the geometry of itself with all the geometry of it's children
        recursively (specifically - those children that are not Blender Object nodes).

        The result will become a single mesh in Blender.

        'texmap' is a texture that applies to this node from a file further up (e.g. a
        texture declared in a model on the line that uses this part), in this node's
        coordinates. It applies to any geometry that has no texture of its own.
        """

        assert self.file is not None

        accumCull = accumCull and self.bfcCull
        accumInvert = accumInvert != self.bfcInverted

        ourColourName = LDrawNode.resolveColour(self.colourName, realColourName)
        code = LDrawNode.getBFCCode(accumCull, accumInvert, self.bfcCull, self.bfcInverted)
        textureCode = "_tx" + texmap.signature() if texmap is not None else ""
        meshName = "Mesh_{0}_{1}{2}{3}".format(basename, ourColourName, code, textureCode)
        key = (self.filename, ourColourName, accumCull, accumInvert, self.bfcCull, self.bfcInverted, textureCode)
        bakedGeometry = CachedGeometry.getCached(key)
        if bakedGeometry is None:
            combinedMatrix = parentMatrix @ self.matrix

            # Start with a copy of our file's geometry
            assert len(self.file.geometry.faces) == len(self.file.geometry.faceInfo)
            bakedGeometry = LDrawGeometry()
            bakedGeometry.appendGeometry(self.file.geometry, Math.identityMatrix, False, self.file.isStud, self.file.isStudLogo, combinedMatrix, self.bfcCull, self.bfcInverted, texmap)

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
                    childTexmap = child.texmap if child.texmap is not None else texmap
                    bakedGeometry.appendGeometry(bg, child.matrix, self.file.isStud, isStud, isStudLogo, combinedMatrix, self.bfcCull, self.bfcInverted, childTexmap)

            CachedGeometry.addToCache(key, bakedGeometry)
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
class LDrawFile:
    """Stores the contents of a single LDraw file.
    Specifically this represents an IO, LDR, L3B, DAT or one '0 FILE' section of an MPD.
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
                if filepath not in globalMissingFiles:
                    globalMissingFiles.append(filepath)
                return False
            filepath = result

        if os.path.splitext(filepath)[1].lower() == ".io":
            ioFilepath = filepath
            if os.path.isdir(filepath):
                # A Stud.io file that has already been unzipped into a folder of the same name
                # (e.g. by double clicking it on a Mac). Use its files where they are.
                directory_to_extract_to = filepath
            else:
                # Check if the file is encrypted (password protected)
                is_encrypted = False
                try:
                    zf = zipfile.ZipFile(filepath)
                except zipfile.BadZipFile:
                    printError("'{0}' is not a Stud.io file that can be read (it isn't a zip file)".format(filepath))
                    return False
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
            if not os.path.isfile(filepath):
                printError("The Stud.io file '{0}' has no model.ldr in it".format(ioFilepath))
                return False

            # Add the subdirectories of the directory to the search paths, notably 'CustomParts' and it's subdirectories

            # Also add the Stud.io 'local' directory for its 'CustomParts' folder
            if Configure.isWindows():
                # But also search CustomParts in: C:\Users\<USERNAME>\AppData\Local\Stud.io\
                localDir = os.path.expanduser(os.path.join("~", "AppData", "Local", "Stud.io"))
            elif Configure.isMac():
                # But also search CustomParts in: ~/.local/share/Stud.io/
                localDir = os.path.expanduser(os.path.join("~", ".local", "share", "Stud.io"))
            else:
                # No Stud.io for Linux
                localDir = None

            for direct in [directory_to_extract_to, localDir]:
                if direct:
                    Configure.appendUnofficialPath(os.path.join(direct, "CustomParts"))
                    Configure.appendUnofficialPath(os.path.join(direct, "CustomParts", "parts"))

                    if Options.resolution == "High":
                        Configure.appendUnofficialPath(os.path.join(direct, "CustomParts", "p", "48"))
                    elif Options.resolution == "Low":
                        Configure.appendUnofficialPath(os.path.join(direct, "CustomParts", "p", "8"))
                    Configure.appendUnofficialPath(os.path.join(direct, "CustomParts", "p"))
                    Configure.appendUnofficialPath(os.path.join(direct, "CustomParts", "s"))
                    Configure.appendUnofficialPath(os.path.join(direct, "CustomParts", "s", "s"))

        self.fullFilepath = filepath

        # Load text into local lines variable
        lines = FileSystem.readTextFile(filepath)
        if lines is None:
            printWarningOnce("Could not read file {0}".format(filepath))
            lines = []

        # MPD files have separate sections between '0 FILE' and '0 NOFILE' lines.
        # Split into sections between "0 FILE" and "0 NOFILE" lines.
        # A '0 !DATA' line starts a section of embedded (base64) data, such as a texture image.
        sections = []

        startLine = 0
        lineCount = 0
        sectionFilename = filepath
        sectionIsData = False
        inSection = True

        for line in lines:
            parameters = line.strip().split()
            if len(parameters) >= 2 and parameters[0] == "0":
                isFileLine = (parameters[1] == "FILE") and (len(parameters) > 2)
                isDataLine = (parameters[1] == "!DATA") and (len(parameters) > 2)
                if isFileLine or isDataLine:
                    if inSection and lineCount > startLine:
                        sections.append((sectionFilename, lines[startLine:lineCount], sectionIsData))

                    startLine = lineCount
                    inSection = True
                    sectionFilename = " ".join(parameters[2:])
                    sectionIsData = isDataLine

                elif parameters[1] == "NOFILE":
                    if inSection:
                        sections.append((sectionFilename, lines[startLine:lineCount], sectionIsData))
                    inSection = False
            lineCount += 1

        if inSection and lineCount > startLine:
            sections.append((sectionFilename, lines[startLine:lineCount], sectionIsData))

        # Decode embedded data, keeping the LDraw sections
        fileSections = []
        for (sectionFilename, sectionLines, sectionIsData) in sections:
            if sectionIsData:
                EmbeddedImages.addSection(sectionFilename, sectionLines, filepath)
            else:
                fileSections.append((sectionFilename, sectionLines))
        sections = fileSections

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

    def __hasLDrawOrgLine(lines):
        for line in lines or []:
            parameters = line.split(None, 2)
            if len(parameters) >= 2 and parameters[0] == "0" and parameters[1] == "!LDRAW_ORG":
                return True
        return False

    def __setTypeFromLocation(self):
        """Sets the file type (part, subpart or primitive) from the folder it is in, e.g. 'parts', 'parts/s' or 'p'."""
        if not getattr(self, "fullFilepath", None) or not self.filename.lower().endswith(".dat"):
            return
        folders = os.path.normpath(os.path.dirname(self.fullFilepath)).lower().split(os.sep)
        folder = folders[-1] if len(folders) > 0 else ""
        parent = folders[-2] if len(folders) > 1 else ""
        if folder == "parts":
            self.isPart = True
        elif folder == "s" and parent == "parts":
            self.isPart = True
            self.isSubPart = True
            self.isSubPartOrPrimitive = True
        elif folder == "p" or (folder in ("48", "8") and parent == "p"):
            self.isSubPart = True
            self.isSubPartOrPrimitive = True

    def isStud(filename):
        """Is this file a stud?"""

        if LDrawFile.isStudLogo(filename):
            return True

        # Extract just the filename, in lower case
        filename = filename.replace("\\", os.path.sep)
        name = os.path.basename(filename).lower()

        return name in (
            "stud.dat",
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

    def isStudLogo(filename):
        """Is this file a stud logo?"""

        # Extract just the filename, in lower case
        filename = filename.replace("\\", os.path.sep)
        name = os.path.basename(filename).lower()

        return name in ("logo3.dat", "logo4.dat", "logo5.dat", "logotente.dat")

    def __init__(self, filename, isFullFilepath, parentFilepath, lines = None, isSubPart=False):
        """Loads an LDraw file (IO, LDR, L3B, DAT or MPD)"""

        global globalCamerasToAdd
        global globalScaleFactor

        self.filename         = filename
        self.lines            = lines
        self.isPart           = False
        self.isSubPart        = isSubPart
        self.isStud           = LDrawFile.isStud(filename)
        self.isStudLogo       = LDrawFile.isStudLogo(filename)
        self.isLSynthPart     = False
        self.isDoubleSided    = False
        self.geometry         = LDrawGeometry()
        self.childNodes       = []
        self.bfcCertified     = None
        self.isModel          = False
        self.isSubPartOrPrimitive = False   # The file says (or its folder implies) it is a subpart or primitive
        self.isShortcut       = False       # A library shortcut (an assembly of parts, e.g. 3829c01)
        self.category         = None        # From '0 !CATEGORY <category>' (e.g. 'Minifig Headwear')

        isGrainySlopeAllowed = not self.isStud

        if self.lines is None:
            # Load the file into self.lines
            if not self.__loadLegoFile(self.filename, isFullFilepath, parentFilepath):
                return
        else:
            # We are loading a section of our parent document, so full filepath is that of the parent
            self.fullFilepath = parentFilepath

        # Some libraries (notably Stud.io's 'UnOfficial' parts) have files without an '0 !LDRAW_ORG' line.
        # Without it a part would be treated as a model, and each of its primitives would become a
        # separate Blender object. So work out the type of file from where it is in the library instead.
        if not LDrawFile.__hasLDrawOrgLine(self.lines):
            self.__setTypeFromLocation()

        # BFC = Back face culling. The rules are arcane and complex, but at least
        #       it's kind of documented: http://www.ldraw.org/article/415.html
        bfcLocalCull          = True
        bfcWindingCCW         = True
        bfcInvertNext         = False
        processingLSynthParts = False
        camera = LDrawCamera()

        currentGroupNames = []
        leocadPieceHidden = False

        # Texture mapping state (!TEXMAP). Each stack entry is [TexMap, inFallback].
        textureStack = []
        nextTexture = None

        #debugPrint("Processing file {0}, isSubPart = {1}, found {2} lines".format(self.filename, self.isSubPart, len(self.lines)))

        for line in self.lines:
            parameters = line.strip().split()

            # Skip empty lines
            if len(parameters) == 0:
                continue

            # Handle texture mapping commands (when textures are off, these are all ignored as comments,
            # and the FALLBACK geometry is used)
            if Options.useTextures and parameters[0] == "0" and len(parameters) > 1:
                if parameters[1] == "!TEXMAP" and len(parameters) > 2:
                    command = parameters[2].upper()
                    if command == "START":
                        textureStack.append([TexMap.parse(parameters[3:], self.fullFilepath), False])
                    elif command == "NEXT":
                        nextTexture = TexMap.parse(parameters[3:], self.fullFilepath)
                    elif command == "FALLBACK":
                        if textureStack:
                            textureStack[-1][1] = True
                    elif command == "END":
                        if textureStack:
                            textureStack.pop()
                    continue

                # Inside the FALLBACK section of a texture we support, skip the fallback geometry
                if any(entry[1] and entry[0].supported for entry in textureStack):
                    continue

                if parameters[1] == "!:":
                    # Geometry only for programs that support textures. Use it if the texture is supported.
                    activeTexture = nextTexture or (textureStack[-1][0] if textureStack else None)
                    if activeTexture is None or not activeTexture.supported:
                        continue
                    parameters = parameters[2:]
                    if len(parameters) == 0:
                        continue
            elif Options.useTextures and any(entry[1] and entry[0].supported for entry in textureStack):
                # Inside the FALLBACK section of a texture we support, skip the fallback geometry
                continue

            # The texture that applies to this line (if any)
            currentTexture = None
            if Options.useTextures and parameters[0] in ("1", "3", "4"):
                candidate = nextTexture or (textureStack[-1][0] if textureStack else None)
                if candidate is not None and candidate.supported:
                    currentTexture = candidate
            if parameters[0] in ("1", "2", "3", "4", "5"):
                nextTexture = None

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
                        self.isSubPartOrPrimitive = True
                    if 'primitive' in partType:
                        self.isSubPart = True
                        self.isSubPartOrPrimitive = True
                    if 'shortcut' in partType:
                        self.isShortcut = True
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
                if parameters[1] == "!CATEGORY" and self.category is None:
                    self.category = " ".join(word for word in parameters[2:] if word) or None

                if parameters[1] == "!LEOCAD":
                    if parameters[2] == "PIECE" and "HIDDEN" in parameters[3:]:
                        leocadPieceHidden = True
                    if parameters[2] == "GROUP":
                        if parameters[3] == "BEGIN":
                            currentGroupNames.append(" ".join(parameters[4:]).strip())
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


            else:
                if self.bfcCertified is None:
                    self.bfcCertified = False

                self.isModel = (not self.isPart) and (not self.isSubPart)

                # Parse a File reference
                if parameters[0] == "1":
                    (x, y, z, a, b, c, d, e, f, g, h, i) = map(float, parameters[2:14])
                    (x, y, z) = Math.scaleMatrix @ mathutils.Vector((x, y, z))
                    localMatrix = mathutils.Matrix( ((a, b, c, x), (d, e, f, y), (g, h, i, z), (0, 0, 0, 1)) )

                    new_filename = " ".join(parameters[14:])
                    new_colourName = parameters[1]

                    det = localMatrix.determinant()
                    if det < 0:
                        bfcInvertNext = not bfcInvertNext
                    canCullChildNode = (self.bfcCertified or self.isModel) and bfcLocalCull and (det != 0)

                    if new_filename != "":
                        newNode = LDrawNode(new_filename, False, self.fullFilepath, new_colourName, localMatrix, canCullChildNode, bfcInvertNext, processingLSynthParts, not self.isModel, False, currentGroupNames)
                        newNode.texmap = currentTexture
                        newNode.hidden = leocadPieceHidden
                        self.childNodes.append(newNode)
                    else:
                        printWarningOnce("In file '{0}', the line '{1}' is not formatted corectly (ignoring).".format(self.fullFilepath, line))
                    leocadPieceHidden = False

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
                    self.geometry.parseFace(parameters, self.bfcCertified and bfcLocalCull, bfcWindingCCW, isGrainySlopeAllowed, currentTexture)
                    assert len(self.geometry.faces) == len(self.geometry.faceInfo)

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

    def __createNodeBasedMaterial(blenderName, col, isSlopeMaterial=False, image=None, wrapU=False):
        """Set Cycles Material Values."""

        # Reuse current material if it exists, otherwise create a new material
        if bpy.data.materials.get(blenderName) is None:
            material = bpy.data.materials.new(blenderName)
        else:
            material = bpy.data.materials[blenderName]

        # Use nodes
        material.use_nodes = True

        if col is not None:
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

            if image is not None:
                BlenderMaterials.__addTexture(nodes, links, image, colour, wrapU)

            BlenderMaterials.__linkUnconnectedNormals(nodes, links)

            material["Lego.isTransparent"] = isTransparent
            return material

        BlenderMaterials.__createCyclesBasic(nodes, links, (1.0, 1.0, 0.0, 1.0), 1.0, "")
        material["Lego.isTransparent"] = False
        return material

    def __addTexture(nodes, links, image, colour, wrapU=False):
        """
        Composites a texture image over the part colour: the image's alpha mixes between the
        colour and the image, and the result feeds the 'Color' input of the material's main
        node group. Outside the image (UVs beyond 0 to 1) the part colour shows.
        With 'wrapU' (a cylindrical or spherical texture that goes all the way round) the image
        repeats around, so it joins up seamlessly, but is still only drawn between V = 0 and 1.
        """
        main = None
        for node in nodes:
            if node.type == 'GROUP' and 'Color' in node.inputs and not node.inputs['Color'].is_linked:
                main = node
                break
        if main is None:
            return

        uvMap = nodes.new('ShaderNodeUVMap')
        uvMap.uv_map = "UVMap"
        uvMap.location = (-760, 300)

        texture = nodes.new('ShaderNodeTexImage')
        texture.image = image
        texture.extension = 'CLIP'
        texture.interpolation = BlenderMaterials.textureInterpolation(image)
        texture.location = (-560, 300)

        mix = nodes.new('ShaderNodeMixRGB')
        mix.blend_type = 'MIX'
        mix.inputs['Color1'].default_value = colour
        mix.location = (-260, 300)

        links.new(uvMap.outputs['UV'], texture.inputs['Vector'])
        links.new(texture.outputs['Color'], mix.inputs['Color2'])
        links.new(mix.outputs['Color'], main.inputs['Color'])

        # The Bevel modifier rounds edges by adding strips of faces, which copy their material and
        # texture coordinates from a neighbouring face. Next to a textured face that would wrap the
        # edge of the print around the rounded edge. So only show the print where the surface
        # faces the same way as the textured face it came from (see addPrintNormals).
        printNormal = nodes.new('ShaderNodeAttribute')
        printNormal.attribute_type = 'GEOMETRY'
        printNormal.attribute_name = PRINT_NORMAL_ATTRIBUTE
        printNormal.location = (-1160, 60)

        geometry = nodes.new('ShaderNodeNewGeometry')
        geometry.location = (-1360, -120)

        toObject = nodes.new('ShaderNodeVectorTransform')
        toObject.vector_type = 'NORMAL'
        toObject.convert_from = 'WORLD'
        toObject.convert_to = 'OBJECT'
        toObject.location = (-1160, -120)

        normalize = nodes.new('ShaderNodeVectorMath')
        normalize.operation = 'NORMALIZE'
        normalize.location = (-960, -120)

        dot = nodes.new('ShaderNodeVectorMath')
        dot.operation = 'DOT_PRODUCT'
        dot.location = (-760, -40)

        absDot = nodes.new('ShaderNodeMath')
        absDot.operation = 'ABSOLUTE'
        absDot.location = (-560, -40)

        facingSameWay = nodes.new('ShaderNodeMath')
        facingSameWay.operation = 'GREATER_THAN'
        facingSameWay.inputs[1].default_value = math.cos(math.radians(PRINT_NORMAL_TOLERANCE_DEGREES))
        facingSameWay.location = (-360, -40)

        # Without the attribute (e.g. a mesh made some other way) the print is always shown
        length = nodes.new('ShaderNodeVectorMath')
        length.operation = 'LENGTH'
        length.location = (-760, 120)

        noAttribute = nodes.new('ShaderNodeMath')
        noAttribute.operation = 'LESS_THAN'
        noAttribute.inputs[1].default_value = 0.5
        noAttribute.location = (-560, 120)

        showPrint = nodes.new('ShaderNodeMath')
        showPrint.operation = 'MAXIMUM'
        showPrint.location = (-360, 120)

        factor = nodes.new('ShaderNodeMath')
        factor.operation = 'MULTIPLY'
        factor.location = (-260, 120)

        links.new(geometry.outputs['True Normal'], toObject.inputs['Vector'])
        links.new(toObject.outputs['Vector'], normalize.inputs[0])
        links.new(normalize.outputs['Vector'], dot.inputs[0])
        links.new(printNormal.outputs['Vector'], dot.inputs[1])
        links.new(dot.outputs['Value'], absDot.inputs[0])
        links.new(absDot.outputs['Value'], facingSameWay.inputs[0])
        links.new(printNormal.outputs['Vector'], length.inputs[0])
        links.new(length.outputs['Value'], noAttribute.inputs[0])
        links.new(facingSameWay.outputs['Value'], showPrint.inputs[0])
        links.new(noAttribute.outputs['Value'], showPrint.inputs[1])
        links.new(texture.outputs['Alpha'], factor.inputs[0])
        links.new(showPrint.outputs['Value'], factor.inputs[1])
        links.new(factor.outputs['Value'], mix.inputs['Fac'])

        if wrapU:
            texture.extension = 'REPEAT'

            separate = nodes.new('ShaderNodeSeparateXYZ')
            separate.location = (-560, 520)

            aboveBottom = nodes.new('ShaderNodeMath')
            aboveBottom.operation = 'GREATER_THAN'
            aboveBottom.inputs[1].default_value = -1e-4
            aboveBottom.location = (-360, 560)

            belowTop = nodes.new('ShaderNodeMath')
            belowTop.operation = 'LESS_THAN'
            belowTop.inputs[1].default_value = 1.0 + 1e-4
            belowTop.location = (-360, 480)

            inside = nodes.new('ShaderNodeMath')
            inside.operation = 'MULTIPLY'
            inside.location = (-160, 520)

            wrappedFactor = nodes.new('ShaderNodeMath')
            wrappedFactor.operation = 'MULTIPLY'
            wrappedFactor.location = (-160, 120)

            links.new(uvMap.outputs['UV'], separate.inputs[0])
            links.new(separate.outputs['Y'], aboveBottom.inputs[0])
            links.new(separate.outputs['Y'], belowTop.inputs[0])
            links.new(aboveBottom.outputs['Value'], inside.inputs[0])
            links.new(belowTop.outputs['Value'], inside.inputs[1])
            links.new(factor.outputs['Value'], wrappedFactor.inputs[0])
            links.new(inside.outputs['Value'], wrappedFactor.inputs[1])
            links.new(wrappedFactor.outputs['Value'], mix.inputs['Fac'])

    __imageCache = {}

    def textureInterpolation(image):
        """
        Small images (pixel art stickers, tiny test images) are drawn pixel sharp. Smoothing them
        would blur each pixel across a large part of the face. Official prints are all larger than
        this and stay smoothed.
        """
        if image is not None:
            longestSide = max(image.size[0], image.size[1])
            if 0 < longestSide <= Options.sharpTextureMaxSize:
                return 'Closest'
        return 'Linear'

    def __writeEmbeddedImage(baseName, data):
        """
        Writes an embedded image next to the imported file. An existing file with the same name
        and different contents is never overwritten, a new name is used instead.
        Returns the filepath, or None if it could not be written.
        """
        folder = os.path.dirname(globalImportFilepath) if globalImportFilepath else ""
        if not folder:
            return None

        stem, extension = os.path.splitext(baseName)
        candidate = baseName
        for attempt in range(1, 100):
            filepath = os.path.join(folder, candidate)
            if not os.path.exists(filepath):
                try:
                    with open(filepath, "wb") as file:
                        file.write(data)
                except OSError as e:
                    printWarningOnce("Could not write the embedded image {0} ({1}), packing it instead".format(filepath, e))
                    return None
                debugPrint("Wrote embedded image {0}".format(filepath))
                return filepath

            # Already there? (e.g. from an earlier import)
            try:
                with open(filepath, "rb") as file:
                    if file.read() == data:
                        return filepath
            except OSError:
                pass
            candidate = "{0}_{1}{2}".format(stem, attempt, extension)
        return None

    def __packedImage(baseName, data):
        """An image packed into the .blend from the given bytes, reusing one from an earlier import of the same bytes"""
        digest = hashlib.sha1(data).hexdigest()
        for image in bpy.data.images:
            if image.get("LDraw.embeddedHash") == digest and image.packed_file is not None:
                return image
        image = bpy.data.images.new(baseName, 1, 1)
        image.source = 'FILE'
        image.filepath_raw = "//textures/" + baseName
        image.pack(data=data, data_len=len(data))
        image["LDraw.embeddedHash"] = digest
        return image

    def __embeddedImage(name, data, sourceFilepath):
        """Creates (or reuses) a Blender image for an image embedded in a '0 !DATA' section"""
        digest = hashlib.sha1(data).hexdigest()
        baseName = os.path.basename(name.strip().replace("\\", "/")) or "embedded.png"
        pack = Options.packEmbeddedImages

        # Reuse the image from an earlier import of the same data
        for image in bpy.data.images:
            if image.get("LDraw.embeddedHash") == digest:
                if pack and image.packed_file is not None:
                    return image
                if not pack and image.packed_file is None and os.path.isfile(bpy.path.abspath(image.filepath)):
                    return image

        image = None
        if not pack:
            filepath = BlenderMaterials.__writeEmbeddedImage(baseName, data)
            if filepath is not None:
                try:
                    image = bpy.data.images.load(filepath, check_existing=True)
                except RuntimeError:
                    image = None

        if image is None:
            # Pack the image data into the .blend file. If unpacked, it goes in a 'textures' folder.
            image = bpy.data.images.new(baseName, 1, 1)
            image.source = 'FILE'
            image.filepath_raw = "//textures/" + baseName
            image.pack(data=data, data_len=len(data))

        image["LDraw.embeddedHash"] = digest
        return image

    def getTextureImage(texmap):
        """Finds and loads the image for a texture. Returns None (with a warning) if it can't be found."""
        rootPath = os.path.dirname(texmap.declaringFilepath) if texmap.declaringFilepath else None
        key = (texmap.imageName.lower(), rootPath)
        if key in BlenderMaterials.__imageCache:
            return BlenderMaterials.__imageCache[key]

        image = None

        # An image embedded in the file ('0 !DATA') comes first
        embedded = EmbeddedImages.get(texmap.imageName)
        if embedded is not None:
            try:
                image = BlenderMaterials.__embeddedImage(texmap.imageName, embedded[0], embedded[1])
            except RuntimeError as e:
                printWarningOnce("Could not load the embedded image '{0}' ({1})".format(texmap.imageName, e))
                image = None

        # The spec says: look for 'textures/<name>' along the search path first, then '<name>'
        for candidate in (("textures/" + texmap.imageName, texmap.imageName) if image is None else ()):
            filepath = FileSystem.locate(candidate, rootPath)
            if filepath is not None and ZipLibrary.contains(filepath):
                # In a zipped parts library: pack the image into the .blend from memory
                data = ZipLibrary.read(filepath)
                if data:
                    try:
                        image = BlenderMaterials.__packedImage(os.path.basename(filepath), data)
                    except RuntimeError:
                        image = None
                    if image is not None:
                        break
                continue
            if filepath is not None and os.path.isfile(filepath):
                try:
                    image = bpy.data.images.load(filepath, check_existing=True)
                except RuntimeError:
                    image = None
                if image is not None:
                    break

        if image is None:
            printWarningOnce("Could not find texture image '{0}'".format(texmap.imageName))
        BlenderMaterials.__imageCache[key] = image
        return image

    def __linkUnconnectedNormals(nodes, links):
        """
        Connects the surface normal to any node group 'Normal' input that is left unconnected.

        Blender 5 passes the default value (0,0,0) of an unconnected group input through to the
        nodes inside the group, rather than letting them use the surface normal as before. This
        stops the Bump nodes inside the 'Slope Texture' and 'Concave Walls' groups from working.
        (See https://github.com/TobyLobster/ImportLDraw/issues/117)
        """
        geometry = None
        for node in list(nodes):
            if node.type == 'GROUP' and 'Normal' in node.inputs and not node.inputs['Normal'].is_linked:
                if geometry is None:
                    geometry = nodes.new('ShaderNodeNewGeometry')
                    geometry.location = (-400, -150)
                links.new(geometry.outputs['Normal'], node.inputs['Normal'])

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

        node.inputs['Subsurface Weight'].default_value = subsurface
        node.inputs['Coat Weight'].default_value = clearcoat
        node.inputs['Coat Roughness'].default_value = clearcoat_roughness
        node.inputs['Transmission Weight'].default_value = transmission

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
        node = nodes.new('ShaderNodeSeparateColor')
        node.mode = 'HSV'
        node.location = x, y
        return node

    def __nodeCombineHSV(nodes, x, y):
        node = nodes.new('ShaderNodeCombineColor')
        node.mode = 'HSV'
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
    def getMaterial(colourName, isSlopeMaterial, texmap=None):
        pureColourName = colourName
        if isSlopeMaterial:
            colourName = colourName + "_s"

        # A textured face gets its own material, named after the image
        image = None
        if texmap is not None:
            image = BlenderMaterials.getTextureImage(texmap)
            if image is not None:
                colourName = colourName + "_tex_" + os.path.splitext(image.name)[0] + ("_wrap" if texmap.wrapU else "")

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
                material = bpy.data.materials[blenderName]
                # Repair materials made by earlier versions (see __linkUnconnectedNormals)
                if material.node_tree is not None:
                    BlenderMaterials.__linkUnconnectedNormals(material.node_tree.nodes, material.node_tree.links)
                return material

        # Create new material
        col = BlenderMaterials.__getColourData(pureColourName)
        material = BlenderMaterials.__createNodeBasedMaterial(blenderName, col, isSlopeMaterial, image, texmap is not None and texmap.wrapU)

        if material is None:
            printWarningOnce("Could not create material for blenderName {0}".format(blenderName))

        # Add material to cache
        BlenderMaterials.__material_list[colourName] = material
        return material

    # **********************************************************************************
    def clearCache():
        BlenderMaterials.__material_list = {}
        BlenderMaterials.__imageCache = {}

    # **********************************************************************************
    def addInputSocket(group, my_socket_type, myname):
        if my_socket_type.endswith("FloatFactor"):
            my_socket_type = my_socket_type[:-6]
        elif my_socket_type.endswith("VectorDirection"):
            my_socket_type = my_socket_type[:-9]
        group.interface.new_socket(name=myname, in_out="INPUT", socket_type=my_socket_type)

    # **********************************************************************************
    def addOutputSocket(group, my_socket_type, myname):
        if my_socket_type.endswith("FloatFactor"):
            my_socket_type = my_socket_type[:-6]
        elif my_socket_type.endswith("VectorDirection"):
            my_socket_type = my_socket_type[:-9]
        group.interface.new_socket(name=myname, in_out="OUTPUT", socket_type=my_socket_type)

    # **********************************************************************************
    def setDefaults(group, name, default_value, min_value, max_value):
        group_inputs = group.nodes["Group Input"].outputs
        group_inputs[name].default_value = default_value
        # TODO: How to set min_value and max_value?

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
        # Blender 4 removed 'Subsurface Color', so use the base colour instead
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
                node_mix1        = BlenderMaterials.__nodeMix(group.nodes, Options.instructionsTransparentOpacity, 400, 100)
                node_mix1.name   = "Opacity"
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
            group, node_input, node_output = BlenderMaterials.__createGroup(groupName, -250, 0, 300, 0, True)
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if Options.instructionsLook:
                node_emission    = BlenderMaterials.__nodeEmission(group.nodes, 0, 0)
                node_transparent = BlenderMaterials.__nodeTransparent(group.nodes, 0, 100)
                node_mix1        = BlenderMaterials.__nodeMix(group.nodes, Options.instructionsTransparentOpacity, 400, 100)
                node_mix1.name   = "Opacity"
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
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketFloatFactor','Luminance')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            node_emit  = BlenderMaterials.__nodeEmission(group.nodes, -242, -123)
            node_mix   = BlenderMaterials.__nodeMix(group.nodes, 0.5, 0, 90)

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
                group.links.new(node_sep_hsv.outputs[0], node_com_hsv.inputs[0])    # Hue
                group.links.new(node_sep_hsv.outputs[1], node_com_hsv.inputs[1])    # Saturation
                group.links.new(node_sep_hsv.outputs[2], node_multiply.inputs[0])   # Value
                group.links.new(node_multiply.outputs[0], node_com_hsv.inputs[2])
                group.links.new(node_com_hsv.outputs['Color'], node_principled.inputs['Base Color'])
                group.links.new(node_com_hsv.outputs['Color'], BlenderMaterials.__getSubsurfaceColor(node_principled))
                group.links.new(node_tex_coord.outputs['Object'], node_tex_wave.inputs['Vector'])
                group.links.new(node_tex_wave.outputs['Fac'], node_color_ramp.inputs['Fac'])
                group.links.new(node_color_ramp.outputs['Color'], node_multiply.inputs[1])
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
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Glitter Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

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
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Speckle Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

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
            BlenderMaterials.addInputSocket(group,'NodeSocketColor','Color')
            BlenderMaterials.addInputSocket(group,'NodeSocketVectorDirection','Normal')

            if BlenderMaterials.usePrincipledShader:
                node_principled = BlenderMaterials.__nodePrincipled(group.nodes, 1.0, 0.05, 0.0, 0.5, 0.0, 0.03, 1.45, 0.0, 45-270, 340-210)
                node_translucent = BlenderMaterials.__nodeTranslucent(group.nodes, -225, -382)
                node_mix = BlenderMaterials.__nodeMix(group.nodes, 0.5, 65, -40)

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
        BlenderMaterials.usePrincipledShader = Options.usePrincipledShaderWhenAvailable

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

        # The node groups may already exist (e.g. from a previous import), so make sure they use the current opacity
        if Options.instructionsLook:
            for name in ('Lego Transparent', 'Lego Transparent Fluorescent'):
                group = bpy.data.node_groups.get(BlenderMaterials.__getGroupName(name))
                if group is not None and "Opacity" in group.nodes:
                    group.nodes["Opacity"].inputs['Fac'].default_value = Options.instructionsTransparentOpacity


# **************************************************************************************
def joinStraightLines(lines, tolerance):
    """
    Edge lines that carry straight on from each other (they share an end point and point in opposite directions
    from it) are joined into one longer line. Returns just the joined lines.
    """
    def key(co):
        return (round(co.x / tolerance), round(co.y / tolerance), round(co.z / tolerance))

    # Union-find over the lines
    group = list(range(len(lines)))
    def find(i):
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i

    # The lines that end at each point, with the direction going away from that point
    ends = {}
    for i, (a, b) in enumerate(lines):
        direction = b - a
        if direction.length <= tolerance:
            continue
        direction.normalize()
        ends.setdefault(key(a), []).append((i, direction))
        ends.setdefault(key(b), []).append((i, -direction))

    joined = False
    for lineEnds in ends.values():
        for (i, d1), (j, d2) in itertools.combinations(lineEnds, 2):
            if d1.dot(d2) < -0.99999:
                group[find(i)] = find(j)
                joined = True
    if not joined:
        return []

    # Each group of joined lines becomes one line, between the furthest points at each end
    members = {}
    for i in range(len(lines)):
        members.setdefault(find(i), []).append(i)

    result = []
    for indices in members.values():
        if len(indices) < 2:
            continue
        origin = lines[indices[0]][0]
        direction = (lines[indices[0]][1] - origin).normalized()
        points = [p for i in indices for p in lines[i]]
        distances = [(p - origin).dot(direction) for p in points]
        result.append((points[distances.index(min(distances))], points[distances.index(max(distances))]))
    return result


# **************************************************************************************
def edgesAlongLines(bm, kd, lines, tolerance):
    """
    Returns the indices of the mesh edges that lie along an edge line, including where the faces split the line
    into several mesh edges (issue #29). A mesh edge whose two vertices are both on a line segment lies along it.
    """
    result = set()
    for p0, p1 in lines + joinStraightLines(lines, tolerance * 0.1):
        direction = p1 - p0
        length = direction.length
        if length <= tolerance:
            continue
        direction /= length

        # The vertices on the line segment (searching the sphere around the line)
        onLine = set()
        for co, index, dist in kd.find_range((p0 + p1) * 0.5, length * 0.5 + tolerance):
            t = (co - p0).dot(direction)
            if -tolerance <= t <= length + tolerance and (co - p0 - direction * t).length <= tolerance:
                onLine.add(index)

        if len(onLine) > 1:
            for index in onLine:
                vert = bm.verts[index]
                for meshEdge in vert.link_edges:
                    if meshEdge.other_vert(vert).index in onLine:
                        result.add(meshEdge.index)
    return result


# **************************************************************************************
def verticesOnLines(bm, lines, tolerance):
    """For each edge line, the mesh vertices on it: {vertex index: distance along the line}"""
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()

    kd = mathutils.kdtree.KDTree(len(bm.verts))
    for i, v in enumerate(bm.verts):
        kd.insert(v.co, i)
    kd.balance()

    result = []
    for p0, p1 in lines + joinStraightLines(lines, tolerance * 0.1):
        direction = p1 - p0
        length = direction.length
        if length <= tolerance:
            continue
        direction /= length

        onLine = {}
        for co, index, dist in kd.find_range((p0 + p1) * 0.5, length * 0.5 + tolerance):
            t = (co - p0).dot(direction)
            if -tolerance <= t <= length + tolerance and (co - p0 - direction * t).length <= tolerance:
                onLine[index] = t
        if len(onLine) > 1:
            result.append(onLine)
    return result


# **************************************************************************************
def joinTJunctionsAlongLines(bm, lines, tolerance):
    """
    Along a line (an edge line, or an open edge of the mesh), the faces on one side often have more vertices than
    the faces on the other side, e.g. a long side face meets the row of faces around a hole. The vertices in the
    middle of the long edge are 'T-junctions': the faces don't share an edge there, so the mesh is open. The Bevel
    modifier can't round an open edge, and bevelling the edges nearby opens a crack between the faces.
    This joins the two sides up, so the faces on both sides share the same edges. Only open edges are changed.
    Returns the number of vertices joined.
    """
    def openEdgesAlongLine(vert, onLine):
        """The open edges from 'vert' that run along the line"""
        return [e for e in vert.link_edges if len(e.link_faces) == 1 and e.other_vert(vert).index in onLine]

    def intoFace(edge):
        """The direction from an open edge into its face (in the plane of the face, at right angles to the edge)"""
        face = edge.link_faces[0]
        along = (edge.verts[1].co - edge.verts[0].co).normalized()
        towards = face.calc_center_median() - edge.verts[0].co
        return (towards - along * towards.dot(along)).normalized(), face.normal

    def stacked(edge1, edge2):
        """True when the faces of two open edges lie on top of each other (e.g. a sticker on a surface), rather
        than meeting at the line. Those must not be joined, or welding would merge or remove faces"""
        into1, normal1 = intoFace(edge1)
        into2, normal2 = intoFace(edge2)
        return abs(normal1.dot(normal2)) > 0.99 and into1.dot(into2) > 0.5

    def canJoin(edges1, edges2):
        return edges1 and edges2 and not any(stacked(e1, e2) for e1 in edges1 for e2 in edges2)

    # 1. Where the two sides almost meet at a vertex, but not quite (two vertices on the line closer than the
    #    tolerance, both at the end of open edges along the line), weld them together. Otherwise the tiny edge
    #    between them limits the width of every bevel on the part (the Bevel modifier's 'Clamp Overlap')
    group = {}
    def find(v):
        while group.get(v, v) != v:
            v = group[v]
        return v

    for onLine in verticesOnLines(bm, lines, tolerance):
        positions = sorted((t, index) for index, t in onLine.items())
        for (ta, a), (tb, b) in zip(positions, positions[1:]):
            if tb - ta >= tolerance:
                continue
            va, vb = bm.verts[a], bm.verts[b]
            if not canJoin(openEdgesAlongLine(va, onLine), openEdgesAlongLine(vb, onLine)):
                continue
            # (vertices of the same face are only welded when they are the two ends of an edge)
            if set(va.link_faces) & set(vb.link_faces) and not any(e.other_vert(va) == vb for e in va.link_edges):
                continue
            ra, rb = find(va), find(vb)
            if ra != rb:
                group[rb] = ra

    targetMap = {v: find(v) for v in group if find(v) != v}
    joined = len(targetMap)
    if targetMap:
        bmesh.ops.weld_verts(bm, targetmap=targetMap)

    # 2. For each open mesh edge along a line, find the vertices of the other side that lie in the middle of it
    onEdgeTolerance = tolerance * 0.2
    splits = {}         # edge -> {vertex: distance from edge.verts[0]}
    for onLine in verticesOnLines(bm, lines, tolerance):
        if len(onLine) < 3:
            continue
        positions = sorted((t, index) for index, t in onLine.items())
        for index in onLine:
            vert = bm.verts[index]
            for meshEdge in vert.link_edges:
                if meshEdge.verts[0] != vert:
                    continue    # (each edge once)
                other = meshEdge.other_vert(vert)
                if other.index not in onLine or len(meshEdge.link_faces) != 1:
                    continue    # (only open edges: a T-junction leaves the mesh open on both sides of the line)
                t0 = onLine[index]
                t1 = onLine[other.index]
                low, high = min(t0, t1) + tolerance, max(t0, t1) - tolerance
                faceVerts = {v for face in meshEdge.link_faces for v in face.verts}
                edgeStart = vert.co
                edgeDirection = (other.co - vert.co).normalized()
                for t, middleIndex in positions:
                    if low < t < high:
                        middle = bm.verts[middleIndex]
                        # (the vertex must be right on the mesh edge, so welding doesn't move the surface)
                        offset = middle.co - edgeStart
                        if middle in faceVerts or (offset - edgeDirection * offset.dot(edgeDirection)).length > onEdgeTolerance:
                            continue
                        # It's a T-junction only if the faces on the other side have an open edge from this vertex
                        # along the line (otherwise the vertex belongs to some other surface that touches the line)
                        if canJoin([meshEdge], openEdgesAlongLine(middle, onLine)):
                            splits.setdefault(meshEdge, {})[middle] = abs(t - t0)

    if not splits:
        return joined

    # Split each edge at its middle vertices (nearest first), then weld the new vertices onto them
    targetMap = {}
    for meshEdge, middles in splits.items():
        start, end = meshEdge.verts[0], meshEdge.verts[1]
        current = meshEdge
        remaining = (end.co - start.co).length
        for middle, distance in sorted(middles.items(), key=lambda item: item[1]):
            fromStart = (middle.co - start.co).length
            if remaining <= 0 or fromStart >= remaining:
                break
            newEdge, newVert = bmesh.utils.edge_split(current, start, fromStart / remaining)
            targetMap[newVert] = middle
            # carry on along the part of the edge between the new vertex and the end
            current = next((e for e in newVert.link_edges if e.other_vert(newVert) == end), None)
            if current is None:
                break
            start = newVert
            remaining = (end.co - start.co).length

    bmesh.ops.weld_verts(bm, targetmap=targetMap)
    return joined + len(targetMap)


# **************************************************************************************
def safeBevelWeights(bm, bevelledEdges, width, safety=0.9):
    """
    Returns a bevel weight for each edge index in 'bevelledEdges': 1, or less where a bevel 'width' wide would
    overlap nearby geometry (the Bevel modifier multiplies its width by the weight).

    This does the job of the Bevel modifier's 'Clamp Overlap', but edge by edge. Clamp Overlap finds the tightest
    spot on the whole mesh and narrows every bevel on it to fit, so one sliver triangle could leave a part with
    almost no bevels at all.
    """
    bm.edges.ensure_lookup_table()
    limit = {index: width for index in bevelledEdges}    # the widest bevel allowed for each edge
    maxSlide = 2.0 * width      # how far a bevel may move a corner (further makes long slivers that can fold over)

    # Where more than two faces meet at an edge (e.g. a sticker sitting on a surface shares the surface's edge),
    # a bevel would tear the faces apart, so those edges, and the bevels that end at them, aren't bevelled
    for index in bevelledEdges:
        edge = bm.edges[index]
        if len(edge.link_faces) > 2 or any(len(e.link_faces) > 2 for v in edge.verts for e in v.link_edges):
            limit[index] = 0.0
        elif len(edge.link_faces) == 2:
            # Where the two faces wind in opposite directions (one is facing the wrong way) the bevel folds over
            loop1, loop2 = edge.link_loops
            if loop1.vert == loop2.vert:
                limit[index] = 0.0
            # A line drawn across a flat surface isn't a corner to round off
            elif abs(edge.link_faces[0].normal.dot(edge.link_faces[1].normal)) > 0.9998:
                limit[index] = 0.0

    for face in bm.faces:
        loops = list(face.loops)
        count = len(loops)

        # The bevel of an edge cuts a strip along it out of the face. Keep the strip clear of the face's other
        # vertices (those alongside the edge, e.g. the far corner of a thin triangle), with room for a bevel
        # coming the other way
        for loop in loops:
            edge = loop.edge
            if edge.index not in limit:
                continue
            start = edge.verts[0].co
            along = edge.verts[1].co - start
            length = along.length
            if length == 0:
                continue
            along /= length
            for other in face.verts:
                if other in edge.verts:
                    continue
                offset = other.co - start
                t = offset.dot(along)
                if 0 < t < length:
                    limit[edge.index] = min(limit[edge.index], 0.5 * (offset - along * t).length)

        for k, loop in enumerate(loops):
            # At this corner of the face, edge 'a' comes in and edge 'b' goes out
            a = loops[k - 1].edge
            b = loop.edge
            aBevelled = a.index in limit
            bBevelled = b.index in limit
            if not (aBevelled or bBevelled):
                continue
            angle = loop.calc_angle()

            if aBevelled and bBevelled:
                # The bevels of both edges meet on the line halfway between them, width / sin(angle/2)
                # from the corner. Keep that well inside the face
                reach = min(min(a.calc_length(), b.calc_length()) * 0.5, maxSlide) * math.sin(angle * 0.5)
                limit[a.index] = min(limit[a.index], reach)
                limit[b.index] = min(limit[b.index], reach)
                continue

            if angle > math.radians(170):
                continue        # (nearly straight on: the bevel steps sideways rather than sliding along the edge)

            # The bevel of one edge slides its corner along the other edge, width / sin(angle) from the corner
            bevelled, slide = (a, b) if aBevelled else (b, a)
            length = slide.calc_length()

            # If there's also a bevel at the far end of that edge, sliding towards us, they share the length
            far = slide.other_vert(loop.vert)
            farIndex = next(i for i, l in enumerate(loops) if l.vert == far)
            farEdges = (loops[farIndex].edge, loops[farIndex - 1].edge)
            if any(farEdge != slide and farEdge.index in limit for farEdge in farEdges):
                length *= 0.5
            limit[bevelled.index] = min(limit[bevelled.index], min(length, maxSlide) * math.sin(angle))

    # Where a bevel changes width at a corner that is nearly straight on (e.g. around a curve), the edges of the
    # two bevels meet far from the corner and fold the face over, so each run of bevelled edges that carry on
    # (within 15 degrees of straight) gets the width of its narrowest edge
    group = {}
    def find(index):
        while group.get(index, index) != index:
            index = group[index]
        return index
    for index in limit:
        edge = bm.edges[index]
        for vert in edge.verts:
            direction = (edge.other_vert(vert).co - vert.co).normalized()
            for other in vert.link_edges:
                if other.index not in limit or other.index == index:
                    continue
                if (other.other_vert(vert).co - vert.co).normalized().dot(direction) < -0.966:
                    a, b = find(index), find(other.index)
                    if a != b:
                        group[b] = a
    narrowest = {}
    for index, allowed in limit.items():
        root = find(index)
        narrowest[root] = min(narrowest.get(root, allowed), allowed)

    allowed = {index: narrowest[find(index)] for index in limit}

    # Where a bevel turns a corner on its own (two bevels meet, e.g. around the rim of a curved face), a sudden
    # change of width twists the bevel, and it can turn its back to the camera, rendering black. So along such
    # chains the width changes gradually: by at most 25% from one edge to the next
    chainPairs = []
    for vert in bm.verts:
        bevels = [edge.index for edge in vert.link_edges if edge.index in limit and limit[edge.index] > 0]
        if len(bevels) == 2:
            chainPairs.append(bevels)
    for attempt in range(200):
        changed = False
        for a, b in chainPairs:
            if allowed[a] > allowed[b] * 1.25 + 1e-12:
                allowed[a] = allowed[b] * 1.25
                changed = True
            elif allowed[b] > allowed[a] * 1.25 + 1e-12:
                allowed[b] = allowed[a] * 1.25
                changed = True
        if not changed:
            break
        # (keeping each straight run the same width)
        for index in limit:
            root = find(index)
            narrowest[root] = min(narrowest[root], allowed[index])
        for index in limit:
            allowed[index] = narrowest[find(index)]

    # Where three or more bevels meet at a corner, the Bevel modifier rounds the corner off evenly only if they are
    # the same width, so they take the width of the narrowest there (just at that corner, so narrow bevels
    # don't narrow every bevel on the part)
    cornerWidth = {}
    for index in limit:
        if allowed[index] > 0:
            for vert in bm.edges[index].verts:
                cornerWidth.setdefault(vert.index, []).append(allowed[index])
    for index in limit:
        for vert in bm.edges[index].verts:
            widths = cornerWidth.get(vert.index, [])
            if len(widths) >= 3:
                allowed[index] = min(allowed[index], min(widths))

    weights = {}
    for index, widest in allowed.items():
        weights[index] = 1.0 if widest >= width else max(0.0, safety * widest / width)
    return weights


# **************************************************************************************
def addSharpEdges(bm, ob, geometry, filename, joinTJunctions=False):
    # Parts without any edge lines (e.g. balls, rubber belts, hose segments) have no sharp
    # edges to add, but we still need to write back the welded vertices and fixed normals
    if not geometry.edges:
        bm.to_mesh(ob.data)

    if geometry.edges:
        global globalScaleFactor
        epsilon = 1 * globalScaleFactor

        # Join up the faces that meet at different vertices along an edge line or an open edge of the mesh. Then
        # the mesh is closed there: it can be bevelled, and a bevel doesn't open a crack between the faces
        if joinTJunctions:
            lines = [(geomEdge[0], geomEdge[1]) for geomEdge in geometry.edges]
            for attempt in range(3):
                bm.edges.ensure_lookup_table()
                openEdges = [(e.verts[0].co.copy(), e.verts[1].co.copy()) for e in bm.edges if len(e.link_faces) == 1]
                if not joinTJunctionsAlongLines(bm, lines + openEdges, 0.1 * globalScaleFactor):
                    break

        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.verts.index_update()     # (welding can leave the indices out of date)
        bm.edges.index_update()

        # Create kd tree for fast "find nearest points" calculation
        kd = mathutils.kdtree.KDTree(len(bm.verts))
        for i, v in enumerate(bm.verts):
            kd.insert(v.co, i)
        kd.balance()

        # The mesh edges between the ends of an edge line (between a vertex near one end and a vertex near the other)
        sharpEdges = set()
        for geomEdge in geometry.edges:
            near0 = [index for (co, index, dist) in kd.find_range(geomEdge[0], epsilon)]
            if not near0:
                continue
            near1 = {index for (co, index, dist) in kd.find_range(geomEdge[1], epsilon)}
            for index in near0:
                vert = bm.verts[index]
                for meshEdge in vert.link_edges:
                    if meshEdge.other_vert(vert).index in near1:
                        sharpEdges.add(meshEdge.index)

        # Also the mesh edges along an edge line that the faces split into several mesh edges (issue #29)
        lines = [(geomEdge[0], geomEdge[1]) for geomEdge in geometry.edges]
        sharpEdges |= edgesAlongLines(bm, kd, lines, 0.1 * globalScaleFactor)

        # Make them sharp (i.e. not smooth)
        for meshEdge in bm.edges:
            if meshEdge.index in sharpEdges:
                meshEdge.smooth = False

        bm.to_mesh(ob.data)

        # Set the bevel weights of the sharp edges (the Bevel modifier uses them)
        # (each edge's weight scales the bevel, so it is small where a full bevel would overlap nearby geometry)
        bevel_weight_attr = ob.data.attributes.new("bevel_weight_edge", "FLOAT", "EDGE")
        weights = safeBevelWeights(bm, sharpEdges, Options.bevelWidth * globalScaleFactor)
        for idx, weight in weights.items():
            bevel_weight_attr.data[idx].value = weight


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
def addPrintNormals(mesh):
    """
    Records, on each corner of each textured face, the normal of that face. Faces the Bevel
    modifier adds copy it from a neighbouring face, so the material can tell a rounded edge
    (whose own normal differs) from the textured face itself, and not draw the print there.
    Call once the mesh is in its final shape.
    """
    if mesh.uv_layers.get("UVMap") is None:
        return
    if PRINT_NORMAL_ATTRIBUTE in mesh.attributes:
        mesh.attributes.remove(mesh.attributes[PRINT_NORMAL_ATTRIBUTE])

    isTextured = [material is not None and "_tex_" in material.name for material in mesh.materials]
    normals = [0.0] * (3 * len(mesh.loops))
    for polygon in mesh.polygons:
        if polygon.material_index < len(isTextured) and isTextured[polygon.material_index]:
            normal = polygon.normal
            for loopIndex in polygon.loop_indices:
                normals[3 * loopIndex:3 * loopIndex + 3] = normal
    attribute = mesh.attributes.new(PRINT_NORMAL_ATTRIBUTE, 'FLOAT_VECTOR', 'CORNER')
    attribute.data.foreach_set("vector", normals)

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
def createSubmodelCollection(name, parentCollection):
    """A new collection for a submodel, inside its parent's collection (Options.submodelCollections)"""
    title = os.path.splitext(os.path.basename(name.replace("\\", "/")))[0] or name
    # Blender names are limited to 63 bytes when encoded as UTF-8
    while len(title.encode("utf8")) > 63:
        title = title[:-1]
    collection = bpy.data.collections.new(title)
    if parentCollection is None:
        parentCollection = getImportCollection()
    parentCollection.children.link(collection)
    return collection

# **************************************************************************************
def addNodeToParentWithGroups(parentObject, groupNames, newObject):
    firstNewObject = len(globalObjectsToAdd)

    if not Options.flattenGroups:
        # Create groups as needed
        for groupName in groupNames:
            # The max length of a Blender node name appears to be 63 bytes when encoded as UTF-8. We make sure it fits.
            while len(groupName.encode("utf8")) > 63:
                groupName = groupName[:-1]

            # Reuse the group node if we have already created it under this parent during this import.
            # (Looking up by name alone would find a group node belonging to a different instance of
            # the same submodel, or to a previous import.)
            key = (parentObject.as_pointer() if parentObject is not None else 0, groupName)
            groupObj = globalGroupObjects.get(key)
            if groupObj is None:
                groupObj = bpy.data.objects.new(groupName, None)
                groupObj.parent = parentObject
                globalObjectsToAdd.append(groupObj)
                globalGroupObjects[key] = groupObj
            parentObject = groupObj

    newObject.parent = parentObject
    globalObjectsToAdd.append(newObject)

    # Remember the submodel collection for the new objects (they are linked at the end of the import)
    if globalCurrentCollection is not None:
        for ob in globalObjectsToAdd[firstNewObject:]:
            globalObjectCollections[ob.as_pointer()] = globalCurrentCollection


# **************************************************************************************
partsHierarchy = {}     # Parent part number -> (list of attach points, set of child part numbers and 'category:' entries)

# **************************************************************************************
def parseParentsFile(file):
    """
    Reads parents.txt (see the description at the top of that file).
    Returns {parent part number: (list of attach points, set of children)}, where children are part
    numbers, or 'category:<category in lower case>' for a 'Category <category>' line.
    """
    # See https://stackoverflow.com/a/53870514
    number_pattern = r"[+-]?((\d+(\.\d*)?)|(\.\d+))"
    compiled = re.compile("(" + number_pattern + r")(\s+|$)(.*)")

    def number_split(s):
        match = compiled.match(s)
        if match is None:
            return None, s
        groups = match.groups()
        return groups[0], groups[-1].strip()

    hierarchy = {}
    groups = {}
    name = None             # current parent part number or group name
    isGroup = False
    attachPoints = []
    children = set()

    def finish():
        if name is None:
            return
        if isGroup:
            groups[name] = children
        else:
            hierarchy[name] = (attachPoints, children)

    with open(file, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for lineNumber, line in enumerate(lines, 1):
        line = line.split("#")[0].strip()
        if not line:
            continue

        def warn(problem):
            printWarningOnce("parents.txt line {0}: {1} '{2}' (ignoring this line)".format(lineNumber, problem, line))

        if line.startswith("Group ") or line.startswith("Parent "):
            finish()
            isGroup = line.startswith("Group ")
            name = line.split(None, 1)[1].strip().strip(":").strip()
            attachPoints = []
            children = set()
            continue

        if name is None:
            warn("Expected 'Parent' or 'Group' before")
            continue

        if line in groups:
            # Use of a group: add its children
            children |= groups[line]
            continue

        if line.startswith("Category "):
            # Any part with this '0 !CATEGORY' (e.g. 'Minifig Headwear')
            children.add("category:" + line.split(None, 1)[1].strip().lower())
            continue

        # An attach point is three numbers
        numbers = []
        rest = line
        while len(numbers) < 4:
            number, rest = number_split(rest)
            if number is None:
                break
            numbers.append(number)

        if len(numbers) == 1 and not rest:
            # A child part number
            children.add(line)
        elif len(numbers) == 3 and not rest:
            if isGroup:
                warn("Groups can't have attach points")
            else:
                attachPoints.append(tuple(float(n) for n in numbers))
        elif not numbers and len(line.split()) == 1:
            # A child part number such as 'u9210', or the name of a group
            if line[:1].isupper() and not re.match(r"[A-Za-z]?\d", line):
                warn("Unknown group")
            else:
                children.add(line)
        else:
            warn("Expected an attach point (three numbers), a part number, a group or 'Category <category>'")

    finish()
    return hierarchy


# **************************************************************************************
def barePartNumber(filename):
    """The part number without any pattern, assembly or other suffix e.g. '3626' for '3626bp01.dat', 'u9210' for 'u9210.dat'"""
    basename = os.path.basename(filename.replace("\\", "/"))
    # Parts embedded in an official model's MPD are named like '60390 - 973p0o.dat'
    if " - " in basename:
        basename = basename.split(" - ", 1)[1]
    m = re.match(r"([A-Za-z]?\d+)($|\D)", basename)
    return m.group(1) if m else ""


# **************************************************************************************
def setupImplicitParents():
    """
    Rigs minifigs: parts that are attached to other parts (e.g. the head to the torso, hair to the head) become
    children of them, using the parents and attach points in parents.txt.
    Only the objects created by this import are considered.
    """
    global globalScaleFactor
    global partsHierarchy

    if not Options.minifigHierarchy:
        return

    partsHierarchy = parseParentsFile(os.path.join(Options.scriptDirectory, 'parents.txt'))
    if not partsHierarchy:
        return

    childParts = set()
    for attachPoints, children in partsHierarchy.values():
        childParts |= children

    def childKeys(partInfo):
        """The ways the children lists can refer to a part: its part number, and its category"""
        partNumber, category = partInfo
        keys = [partNumber]
        if category:
            keys.append("category:" + category.lower())
        return keys

    # The parents and possible children among the objects of this import
    parentObjects = []
    childObjects = []
    for obj in globalObjectsToAdd:
        if obj.type != 'MESH':
            continue
        partInfo = globalObjectParts.get(obj.as_pointer())
        if partInfo is None:
            continue
        if partInfo[0] in partsHierarchy:
            parentObjects.append((obj, partInfo[0]))
        if any(key in childParts for key in childKeys(partInfo)):
            childObjects.append((obj, childKeys(partInfo)))

    if not parentObjects or not childObjects:
        return

    bpy.context.view_layer.update()

    tolerance = globalScaleFactor * 5 # in LDraw units
    squaredTolerance = tolerance * tolerance

    # For each child, find the closest attach point of a parent that accepts it
    bestParent = {}     # child object pointer -> (squared distance, parent object, child object)
    for obj, partNumber in parentObjects:
        attachPoints, children = partsHierarchy[partNumber]
        slotLocations = [obj.matrix_world @ (mathutils.Vector(slot) * globalScaleFactor) for slot in attachPoints]
        if not slotLocations:
            continue

        for childObj, keys in childObjects:
            if childObj == obj or not any(key in children for key in keys):
                continue
            childLocation = childObj.matrix_world.to_translation()
            squaredDistance = min((slotLocation - childLocation).length_squared for slotLocation in slotLocations)
            if squaredDistance <= squaredTolerance:
                best = bestParent.get(childObj.as_pointer())
                if best is None or squaredDistance < best[0]:
                    bestParent[childObj.as_pointer()] = (squaredDistance, obj, childObj)

    # Parent them (closest first), never making a loop of parents
    newParents = {}
    for squaredDistance, obj, childObj in sorted(bestParent.values(), key=lambda entry: entry[0]):
        ancestor = obj
        while ancestor is not None and ancestor != childObj:
            ancestor = newParents.get(ancestor.as_pointer(), ancestor.parent)
        if ancestor == childObj:
            continue
        newParents[childObj.as_pointer()] = obj

    for squaredDistance, obj, childObj in bestParent.values():
        if newParents.get(childObj.as_pointer()) == obj:
            # Keep the child exactly where it is, by setting the parent inverse matrix (as Ctrl+P does), rather
            # than setting matrix_world, which loses any shear in the LDraw matrices and slightly turns the part
            oldParentMatrix = childObj.parent.matrix_world.copy() if childObj.parent else mathutils.Matrix.Identity(4)
            parentInverse = obj.matrix_world.inverted_safe() @ oldParentMatrix @ childObj.matrix_parent_inverse
            childObj.parent = obj
            childObj.matrix_parent_inverse = parentInverse

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

            mesh.validate()
            mesh.update()

            # Add texture coordinates if any face is textured
            if any(faceInfo.uvs is not None for faceInfo in geometry.faceInfo):
                assert len(mesh.polygons) == len(geometry.faces)
                uvLayer = mesh.uv_layers.new(name="UVMap")
                uvs = [0.0] * (2 * len(mesh.loops))
                for polygon, faceInfo in zip(mesh.polygons, geometry.faceInfo):
                    if faceInfo.uvs is None:
                        continue
                    for corner, loopIndex in enumerate(polygon.loop_indices):
                        uvs[2 * loopIndex], uvs[2 * loopIndex + 1] = faceInfo.uvs[corner]
                uvLayer.data.foreach_set("uv", uvs)

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
                material = BlenderMaterials.getMaterial(faceColour, isSlopeMaterial, faceInfo.texmap)

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
        # Each edge's bevel weight already keeps its bevel from overlapping (see safeBevelWeights), whereas
        # Clamp Overlap would narrow every bevel on the part to fit the tightest spot
        bevelModifier.use_clamp_overlap = False

    # Add edge split modifier to each instance
    if Options.edgeSplit:
        edgeModifier = ob.modifiers.new("Edge Split", type='EDGE_SPLIT')
        edgeModifier.use_edge_sharp = True
        edgeModifier.split_angle = math.radians(30.0)

# **************************************************************************************
def smoothShadingAndFreestyleEdges(ob):
    # (Set directly on the mesh: the Shade Smooth operator needed the object in the scene and selected, and
    # operators get slower as the scene grows)

    # Smooth shading
    if Options.smoothShading and len(ob.data.polygons) > 0:
        ob.data.polygons.foreach_set("use_smooth", [True] * len(ob.data.polygons))
        # (Since Blender 4.1 flat faces are stored as a 'sharp_face' attribute, which is now all False, so as
        # Shade Smooth does, the attribute is removed)
        sharpFaces = ob.data.attributes.get("sharp_face")
        if sharpFaces is not None:
            ob.data.attributes.remove(sharpFaces)

    if Options.instructionsLook:
        # Mark all sharp edges as freestyle edges
        me = ob.data
        if len(me.edges) > 0:
            sharp = [False] * len(me.edges)
            me.edges.foreach_get("use_edge_sharp", sharp)
            if hasattr(me.edges[0], 'use_freestyle_mark'):
                # Before Blender 5
                me.edges.foreach_set("use_freestyle_mark", sharp)
            else:
                # Blender 5 stores freestyle edge marks in a boolean edge attribute
                attr = me.attributes.get("freestyle_edge")
                if attr is None:
                    attr = me.attributes.new("freestyle_edge", 'BOOLEAN', 'EDGE')
                attr.data.foreach_set("value", sharp)


# **************************************************************************************
def createBlenderObjectsFromNode(node,
                                 localMatrix,
                                 name,
                                 realColourName=None,
                                 blenderParentTransform=Math.identityMatrix,
                                 localToWorldSpaceMatrix=Math.identityMatrix,
                                 blenderNodeParent=None,
                                 texmap=None,
                                 hidden=False):
    """
    Creates a Blender Object for the node given and (recursively) for all it's children as required.
    'hidden' is True inside a piece (e.g. a submodel) that LeoCAD marked as hidden.
    Creates and optimises the mesh for each object too.
    'texmap' is a texture from further up the hierarchy that applies to this node, in the node's coordinates.
    """

    global globalBrickCount
    global globalObjectsToAdd
    global globalWeldDistance
    global globalPoints
    global globalCurrentCollection

    realColourName = realColourName or Options.defaultColour
    ob = None
    previousCollection = globalCurrentCollection
    hidden = hidden or node.hidden

    if node.isBlenderObjectNode():
        ourColourName = LDrawNode.resolveColour(node.colourName, realColourName)
        meshName, geometry = node.getBlenderGeometry(ourColourName, name, texmap=texmap)
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

        # The lines out of an empty shown in the viewport are scaled to a reasonable size
        ob.empty_display_size = 250.0 * globalScaleFactor

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

        # Remember which part this is, for rigging minifigs (see setupImplicitParents)
        if Options.minifigHierarchy and not node.file.isModel:
            globalObjectParts[ob.as_pointer()] = (barePartNumber(name), node.file.category)

        # Submodels as collections: the model's object, and everything inside it, go in a new collection
        if Options.submodelCollections and node.file.isModel and not node.file.isShortcut and not Options.flattenHierarchy:
            globalCurrentCollection = createSubmodelCollection(name, previousCollection)
            globalObjectCollections[ob.as_pointer()] = globalCurrentCollection

        # Node to which our children will be attached
        blenderNodeParent = ob
        blenderParentTransform = Math.identityMatrix

        # debugPrint("NAME = {0}".format(name))

        # Add light to light bricks
        lightBrickName = name.lower()
        if lightBrickName in globalLightBricks:
            # The lamp's position, size and strength were set up for a realScale of 100, so scale them to match the model
            lampScale = Options.realScale / 100.0
            lights = bpy.data.lights
            lamp_data = lights.new(name="LightLamp", type='POINT')
            lamp_data.shadow_soft_size = 0.05 * lampScale
            lamp_data.use_nodes = True
            emission_node = lamp_data.node_tree.nodes.get('Emission')
            if emission_node:
                emission_node.inputs['Color'].default_value = globalLightBricks[lightBrickName]
                # Light falls off with the square of distance, so the strength scales with the square of the size
                emission_node.inputs['Strength'].default_value = 100.0 * lampScale * lampScale
            lamp_object = bpy.data.objects.new(name="LightLamp", object_data=lamp_data)
            lamp_object.location = (-0.27 * lampScale, 0.0, -0.18 * lampScale)

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
            if removeDoubles:
                bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=globalWeldDistance)

            # Recalculate normals
            if recalculateNormals:
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])

            # Add sharp edges and edge weights
            addSharpEdges(bm, ob, geometry, name, joinTJunctions=removeDoubles and Options.joinTJunctions)

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
                # Options.realGapWidth is a real life size, so scale it to match the model
                gapWidth = Options.realGapWidth * Options.realScale
                gapHeight = 0.33 * gapWidth
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
                    scaleFac.x = 1 - gapWidth  * abs(objScale.x) / dim.x
                if dim.y != 0:
                    scaleFac.y = 1 - gapHeight            * abs(objScale.y) / dim.y
                if dim.z != 0:
                    scaleFac.z = 1 - gapWidth  * abs(objScale.z) / dim.z

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

            addPrintNormals(mesh)

            smoothShadingAndFreestyleEdges(ob)

        # Keep track of all vertices in global space, for positioning the camera and/or root object at the end
        # Notice that we do this after scaling for Options.gaps
        # Hidden pieces are hidden in the viewport and in renders (once in the scene)
        if hidden:
            globalHiddenObjects.append(ob)

        # (Hidden pieces don't count when placing the model on the ground or framing the camera)
        if (Options.positionObjectOnGroundAtOrigin or Options.positionCamera) and not hidden:
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

        # A texture on the line that uses the child, or else one that applies to us, applies to the child
        childTexmap = childNode.texmap if childNode.texmap is not None else texmap
        if childTexmap is not None:
            childTexmap = childTexmap.transformed(childNode.matrix)

        createBlenderObjectsFromNode(childNode, childNode.matrix, childNode.filename, childColourName, blenderParentTransform, localToWorldSpaceMatrix @ localMatrix, blenderNodeParent, childTexmap, hidden)

    globalCurrentCollection = previousCollection
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
    lineset.select_by_collection = True
    lineset.collection = bpy.data.collections[bpy.data.collections.find(group)]

    # Set line color
    lineset.linestyle.color = (0.0, 0.0, 0.0)

    # Set material to override color
    if 'LegoMaterial' not in lineset.linestyle.color_modifiers:
        lineset.linestyle.color_modifiers.new('LegoMaterial', 'MATERIAL')

    # Use square caps
    lineset.linestyle.caps = 'SQUARE'       # Can be 'ROUND', 'BUTT', or 'SQUARE'

    # Draw centered on the edge of the object
    lineset.linestyle.thickness_position = 'CENTER'

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

        # Turn off film transparency
        render.film_transparent = False

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
        if hasattr(scene, "compositing_node_group"):
            # Blender 5
            node_tree = bpy.data.node_groups.new("Compositor Nodes", "CompositorNodeTree")
            scene.compositing_node_group = node_tree
        elif hasattr(scene, "node_tree"):
            # Before Blender 5
            node_tree = scene.node_tree

        # If scene nodes exist for compositing instructions look, remove them
        nodeNames = [node.name for node in node_tree.nodes]
        if "Solid" in nodeNames:
           node_tree.nodes.remove(node_tree.nodes["Solid"])

        if "Trans" in nodeNames:
           node_tree.nodes.remove(node_tree.nodes["Trans"])

        # (Blender 5 names this node "Depth Combine" by default)
        for zCombineName in ("Z Combine", "Depth Combine"):
            if zCombineName in nodeNames:
                node_tree.nodes.remove(node_tree.nodes[zCombineName])

        # Set up standard link from Render Layers to Composite
        if "Render Layers" in nodeNames:
            if "Composite" in nodeNames:
                rl = node_tree.nodes["Render Layers"]
                zCombine = node_tree.nodes["Composite"]

                links = node_tree.links
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
def ensure_output_color_socket(node_tree, name="Result"):
    iface = node_tree.interface

    # items_tree holds the sockets and panels of the interface
    for item in iface.items_tree:
        if getattr(item, "item_type", None) == 'SOCKET' and item.name == name and item.in_out == 'OUTPUT':
            return item

    # not found — create and return new socket
    return iface.new_socket(name=name, in_out='OUTPUT', socket_type='NodeSocketColor')

# **************************************************************************************
def setupInstructionsLook():
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

    # Turn on film transparency
    render.film_transparent = True

    # Increase max number of transparency bounces to at least 80
    # This avoids artefacts when multiple transparent objects are behind each other
    if scene.cycles.transparent_max_bounces < 80:
        scene.cycles.transparent_max_bounces = 80

    # Add collections, if not already present
    createCollection(scene, 'Black Edged Bricks Collection')
    createCollection(scene, 'White Edged Bricks Collection')
    createCollection(scene, 'Solid Bricks Collection')
    createCollection(scene, 'Transparent Bricks Collection')

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

    # Use Z layer (defaults to off)
    layers[transLayer].use_pass_z = True
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
    if hasattr(scene, "compositing_node_group"):
        # Blender 5
        if "Compositor Nodes" in bpy.data.node_groups:
            node_tree = bpy.data.node_groups["Compositor Nodes"]
        else:
            node_tree = bpy.data.node_groups.new("Compositor Nodes", "CompositorNodeTree")
        scene.compositing_node_group = node_tree
    elif hasattr(scene, "node_tree"):
        # Before Blender 5
        node_tree = scene.node_tree

    if hasattr(node_tree, "nodes"):
        if "Solid" in node_tree.nodes:
            solidLayer = node_tree.nodes["Solid"]
        else:
            solidLayer = node_tree.nodes.new('CompositorNodeRLayers')
            solidLayer.name = "Solid"
        solidLayer.layer = 'SolidBricks'

        if "Trans" in node_tree.nodes:
            transLayer = node_tree.nodes["Trans"]
        else:
            transLayer = node_tree.nodes.new('CompositorNodeRLayers')
            transLayer.name = "Trans"
        transLayer.layer = 'TransparentBricks'

        # Reuse our existing node if present (Blender 5 names this node "Depth Combine" by default)
        zCombine = node_tree.nodes.get("Z Combine") or node_tree.nodes.get("Depth Combine")
        if zCombine is None:
            zCombine = node_tree.nodes.new('CompositorNodeZcombine')
            zCombine.name = "Z Combine"

        if hasattr(zCombine, "use_alpha"):
            zCombine.use_alpha = True
        else:
            # Blender 5
            zCombine.inputs["Use Alpha"].default_value = True

        if hasattr(zCombine, "use_antialias_z"):
            zCombine.use_antialias_z = True
        else:
            # Blender 5
            zCombine.inputs["Anti-Alias"].default_value = True

        if "Set Alpha" in node_tree.nodes:
            setAlpha = node_tree.nodes["Set Alpha"]
        else:
            setAlpha = node_tree.nodes.new('CompositorNodeSetAlpha')
        setAlpha.inputs[1].default_value = 0.75

        if "Composite" in node_tree.nodes:
            # Before Blender 5
            composite = node_tree.nodes["Composite"]
            viewer = None
        else:
            # Blender 5

            new_socket = ensure_output_color_socket(node_tree, 'Result')

            # Remove any existing Group Output node(s)
            for n in tuple(node_tree.nodes):
                if n.bl_idname == "NodeGroupOutput":
                    node_tree.nodes.remove(n)

            group_output = node_tree.nodes.new("NodeGroupOutput")
            composite = group_output

            # Add viewer node (reusing any existing one)
            viewers = [n for n in node_tree.nodes if n.bl_idname == 'CompositorNodeViewer']
            viewer = viewers[0] if viewers else node_tree.nodes.new('CompositorNodeViewer')

        composite.location = (950, 400)

        zCombine.location = (750, 500)
        transLayer.location = (300, 300)
        solidLayer.location = (300, 600)
        setAlpha.location = (580, 400)

        links = node_tree.links
        links.new(solidLayer.outputs[0], zCombine.inputs[0])
        links.new(solidLayer.outputs[2], zCombine.inputs[1])
        links.new(transLayer.outputs[0], setAlpha.inputs[0])
        links.new(setAlpha.outputs[0], zCombine.inputs[2])
        links.new(transLayer.outputs[2], zCombine.inputs[3])
        links.new(zCombine.outputs[0], composite.inputs[0])
        if viewer:
            viewer.location = (950, 500)
            links.new(zCombine.outputs[0], viewer.inputs[0])


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

    depsgraph = bpy.context.evaluated_depsgraph_get()
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
def loadFromFile(context, filename, isFullFilepath=True):
    global globalCamerasToAdd
    global globalContext
    global globalScaleFactor

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
    # reduce the size of each piece by 0.1mm (default amount) to allow
    # for a small gap between pieces. This matches real piece sizes.
    #
    # 3. Blender Scene Unit Scale:
    #
    # Blender has a 'Scene Unit Scale' value which by default is set
    # to 1.0. By changing the 'Unit Scale' after import the size of
    # everything in the scene can be adjusted.

    global globalWeldDistance

    globalScaleFactor = 0.0004 * Options.realScale

    # Vertices closer than this are merged. 0.00125 LDraw units is the distance previously used at
    # realScale 1.0, but now it scales with the model so welding works the same at any scale.
    globalWeldDistance = 0.00125 * globalScaleFactor

    globalCamerasToAdd = []
    globalContext = context

    global globalMissingFiles
    globalMissingFiles = []

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
    EmbeddedImages.clearCache()
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
        addFileToCache("studtente-logo.dat", "s\\teton.dat")     # TENTE

    # Load and parse file to create geometry
    filename = os.path.expanduser(filename)

    global globalImportFilepath
    globalImportFilepath = os.path.abspath(filename) if isFullFilepath else ""

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
            # A texture on the child's line is in the model's (unrotated) coordinates
            if childNode.texmap is not None:
                childNode.texmap = childNode.texmap.transformed(Math.rotationMatrix.inverted())

    # Switch to Object mode and deselect all
    if bpy.ops.object.mode_set.poll():
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')

    name = os.path.basename(filename)

    global globalBrickCount
    global globalObjectsToAdd
    global globalPoints

    global globalGroupObjects
    global globalCurrentCollection
    global globalObjectCollections

    globalBrickCount = 0
    globalObjectsToAdd = []
    globalGroupObjects = {}
    globalCurrentCollection = None
    globalObjectCollections = {}
    global globalHiddenObjects
    globalHiddenObjects = []
    global globalObjectParts
    globalObjectParts = {}
    globalPoints = []

    debugPrint("Creating NodeGroups")
    BlenderMaterials.createBlenderNodeGroups()

    # Create Blender objects from the loaded file
    debugPrint("Creating Blender objects")
    rootOb = createBlenderObjectsFromNode(node, node.matrix, name)

    # Say clearly if files were missing, since the result can be incomplete or even empty
    # (e.g. a part that needs subparts newer than the LDraw library in use)
    if globalMissingFiles:
        hasGeometry = any(ob.type == 'MESH' for ob in globalObjectsToAdd)
        shown = ", ".join(globalMissingFiles[:5]) + (" and {0} more".format(len(globalMissingFiles) - 5) if len(globalMissingFiles) > 5 else "")
        message = "{0} {1} could not be found in the LDraw library at '{2}': {3}".format(
            len(globalMissingFiles), "file" if len(globalMissingFiles) == 1 else "files", Configure.ldrawInstallDirectory, shown)
        if hasGeometry:
            printWarningOnce(message + ". The import may be incomplete.")
            if globalContext is None:
                ShowMessageBox(message + ". The import may be incomplete.", "Import LDraw", 'ERROR')
        else:
            printError(message + ". Nothing could be imported; the library may be too old for this file.")
    elif not any(ob.type == 'MESH' for ob in globalObjectsToAdd):
        # Nothing went wrong, but there is nothing to see
        message = ("'{0}' has no parts or other geometry in it, so nothing visible was imported. "
                   "(Only the first model in a multi-part (.mpd) file is imported, with the parts and submodels it uses.)").format(os.path.basename(filename))
        printWarningOnce(message)
        if globalContext is None:
            ShowMessageBox(message, "Import LDraw", 'ERROR')

    if not node.file.isModel:
        # Fix top level rotation from LDraw coordinate space to Blender coordinate space.
        # We rotate the object rather than its mesh, since the mesh can be shared with other
        # objects (e.g. from a previous import) and must stay in LDraw orientation.
        rootOb.matrix_local = Math.rotationMatrix @ rootOb.matrix_local

        # The points recorded for positioning the camera were in LDraw orientation too
        globalPoints = [Math.rotationMatrix @ p for p in globalPoints]

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

    # Frame the camera and view on what was imported (a model or a single part)
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

        # Length of bounding box diagonal
        boundingBoxDistance = (boundingBoxMax - boundingBoxMin).length
        boundingBoxCentre = (boundingBoxMax + boundingBoxMin) * 0.5

        vcentre = (boundingBoxMin + boundingBoxMax) * 0.5
        offsetToCentreModel = mathutils.Vector((-vcentre.x, -vcentre.y, -boundingBoxMin.z))
        if Options.positionObjectOnGroundAtOrigin:
            debugPrint("Centre object")
            rootOb.location += offsetToCentreModel

            # Offset bounding box
            boundingBoxMin += offsetToCentreModel
            boundingBoxMax += offsetToCentreModel
            boundingBoxCentre += offsetToCentreModel

            # Offset all points
            globalPoints = [p + offsetToCentreModel for p in globalPoints]
            offsetToCentreModel = mathutils.Vector((0, 0, 0))

        if camera is not None:
            if Options.positionCamera:
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

                # Make sure no part of a small model is nearer the camera than the clipping distance.
                # (An orthographic camera can simply move back, since that doesn't change the picture.
                # A perspective camera would change the picture, so it clips less instead.)
                if globalPoints:
                    forwards = camera.rotation_euler.to_matrix() @ mathutils.Vector((0.0, 0.0, -1.0))
                    nearest = min((p - camera.location).dot(forwards) for p in globalPoints)
                    wanted = 2.0 * camera.data.clip_start
                    if nearest < wanted:
                        if camera.data.type == 'ORTHO':
                            camera.location -= forwards * (wanted - nearest)
                        elif nearest > 0.0:
                            camera.data.clip_start = 0.5 * nearest

        # Find the (first) 3D View, then set the view's 'look at' and 'distance'
        # Note: Not a camera object, but the point of view in the UI.
        areas = [area for area in bpy.context.window.screen.areas if area.type == 'VIEW_3D']
        if len(areas) > 0:
            area = areas[0]
            with bpy.context.temp_override(area=area):
                view3d = bpy.context.space_data
                view3d.region_3d.view_location = boundingBoxCentre      # Where to look at
                view3d.region_3d.view_distance = boundingBoxDistance    # How far from target

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
        collection = globalObjectCollections.get(ob.as_pointer())
        if collection is None:
            linkToScene(ob)
        elif collection.objects.find(ob.name) < 0:
            collection.objects.link(ob)

    # Pieces hidden in LeoCAD: hidden in the viewport (the eye in the Outliner) and in renders
    for ob in globalHiddenObjects:
        ob.hide_render = True
        try:
            ob.hide_set(True)
        except RuntimeError:
            ob.hide_viewport = True

    # Parent only once everything has been added to the scene, otherwise the matrix_world's are
    # sometimes not updated properly - some are erroneously still the identity matrix.
    setupImplicitParents()

    # Add cameras to the scene
    for ob in globalCamerasToAdd:
        cam = ob.createCameraNode()
        cam.parent = rootOb

    globalObjectsToAdd = []
    globalCamerasToAdd = []

    # Select the newly created root object
    selectObject(rootOb)

    # Get existing object names
    sceneObjectNames = [x.name for x in scene.objects]

    # Add ground plane with white material
    if Options.addGroundPlane and not Options.instructionsLook:
        if "LegoGroundPlane" not in sceneObjectNames:
            groundPlane = addPlane((0,0,0), 100000 * globalScaleFactor, "LegoGroundPlane")

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

            groundPlane.data.materials.append(material)

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

    debugPrint("Load Done")
    return rootOb
