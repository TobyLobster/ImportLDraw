# -*- coding: utf-8 -*-
"""Import LDraw GPLv2 license.

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

This file defines the importer for Blender.
It stores and recalls preferences for the importer.
The execute() function kicks off the import process.
The python module loadldraw does the actual work.
"""

import configparser
import os
import bpy
from bpy.props import (StringProperty,
                       FloatProperty,
                       EnumProperty,
                       BoolProperty
                       )
from bpy_extras.io_utils import ImportHelper
from .loadldraw import loadldraw

"""
Example preferences file:

[DEFAULT]

[importldraw]
ldrawDirectory     = ""
scale              = 0.04
resolution         = "Standard"
smoothShading      = True
useColourScheme    = "lgeo"
gaps               = True
gapWidth           = 0.04
createInstances    = True
numberNodes        = True
positionObjectOnGroundAtOrigin = True
flattenHierarchy   = False
useUnofficialParts = True
useLogoStuds       = False
instanceStuds      = False
"""


class Preferences():
    """Import LDraw - Preferences"""
    __sectionName   = 'importldraw'

    def __init__(self):
        self.__ldPath        = None
        self.__prefsPath     = os.path.dirname(__file__)
        self.__prefsFilepath = os.path.join(self.__prefsPath, "ImportLDrawPreferences.ini")
        self.__config        = configparser.ConfigParser()
        self.__prefsRead     = self.__config.read(self.__prefsFilepath)
        if self.__prefsRead and not self.__config[Preferences.__sectionName]:
            self.__prefsRead = False

    def get(self, option, default):
        if not self.__prefsRead:
            return default
        
        if type(default) is bool:
            return self.__config.getboolean(Preferences.__sectionName, option, fallback=default)
        elif type(default) is float:
            return self.__config.getfloat(Preferences.__sectionName, option, fallback=default)
        elif type(default) is int:
            return self.__config.getint(Preferences.__sectionName, option, fallback=default)
        else:
            return self.__config.get(Preferences.__sectionName, option, fallback=default)

    def set(self, option, value):
        if not (Preferences.__sectionName in self.__config):
            self.__config[Preferences.__sectionName] = {}
        self.__config[Preferences.__sectionName][option] = str(value)

    def save(self):
        try:
            with open(self.__prefsFilepath, 'w') as configfile:
                self.__config.write(configfile)
            return True
        except Exception:
            # Fail gracefully
            e = sys.exc_info()[0]
            debugPrint("WARNING: Could not save preferences. {0}".format(e))
            return False


class ImportLDrawOps(bpy.types.Operator, ImportHelper):
    """Import LDraw - Import Operator."""

    bl_idname       = "import_scene.importldraw"
    bl_description  = "Import LDraw models (.mpd/.ldr/.l3b/.dat)"
    bl_label        = "Import LDraw Models"
    bl_space_type   = "PROPERTIES"
    bl_region_type  = "WINDOW"
    bl_options      = {'REGISTER', 'UNDO', 'PRESET'}

    # Instance the preferences system
    prefs = Preferences()

    # File type filter in file browser
    filename_ext = ".ldr"
    filter_glob = StringProperty(
        default="*.mpd;*.ldr;*.l3b;*.dat",
        options={'HIDDEN'}
    )

    ldrawPath = StringProperty(
        name="",
        description="Full filepath to the LDraw Parts Library (download from http://www.ldraw.org)",
        default=prefs.get("ldrawDirectory", loadldraw.Configure.findDefaultLDrawDirectory())
    )

    importScale = FloatProperty(
        name="Scale",
        description="Sets a scale for the model.",
        default=prefs.get("scale", 0.01)
    )

    resPrims = EnumProperty(
        name="Resolution of part primitives",
        description="Resolution of part primitives, ie. how much geometry they have",
        default=prefs.get("resolution", "Standard"),
        items=(
            ("Standard", "Standard primitives",        "Import using standard resolution primitives"),
            ("High",     "High resolution primitives", "Import using high resolution primitives."),
            ("Low",      "Low resolution primitives",  "Import using low resolution primitives.")
        )
    )

    smoothParts = BoolProperty(
        name="Smooth faces and edge-split",
        description="Smooth faces and add an edge-split modifier",
        default=prefs.get("smoothShading", True)
    )

    colourScheme = EnumProperty(
        name="Colour scheme options",
        description="Colour scheme options",
        default=prefs.get("useColurScheme", "lgeo"),
        items=(
            ("lgeo", "Realistic colours", "Uses the LGEO colour scheme for realistic colours."),
            ("ldraw", "Original LDraw colours", "Uses the standard LDraw colour scheme."),
            ("alt", "Alternate LDraw colours", "Uses the alternate LDraw colour scheme."),
        )
    )

    addGaps = BoolProperty(
        name="Add space between each part:",
        description="Add a small space between each part",
        default=prefs.get("gaps", True)
    )

    gapsSize = FloatProperty(
        name="Space",
        description="Amount of space between each part",
        default=prefs.get("gapWidth", 0.01)
    )

    linkParts = BoolProperty(
        name="Link identical parts",
        description="Identical parts (same type and colour) share the same mesh",
        default=prefs.get("createInstances", True)
    )

    numberNodes = BoolProperty(
        name="Number each object",
        description="Each object has a five digit prefix eg. 00001_car. This keeps the list in it's proper order.",
        default=prefs.get("numberNodes", True)
    )

    positionOnGround = BoolProperty(
        name="Put model on ground at origin",
        description="The object is centred at the origin, and on the ground plane.",
        default=prefs.get("positionObjectOnGroundAtOrigin", True)
    )
    
    flatten = BoolProperty(
        name="Flatten tree",
        description="In Scene Outliner, all parts are placed directly below the root - there's no tree of submodels",
        default=prefs.get("flattenHierarchy", False)
    )

    useUnofficialParts = BoolProperty(
        name="Include unofficial parts",
        description="Additionally searches for parts in the <ldraw-dir>/unofficial/ directory",
        default=prefs.get("useUnofficialParts", True)
    )

    useLogoStuds = BoolProperty(
        name="Show 'LEGO' logo on studs",
        description="Shows the LEGO logo on each stud (at the expense of some extra geometry and import time).",
        default=prefs.get("useLogoStuds", False)
    )

    instanceStuds = BoolProperty(
        name="Make individual studs",
        description="Creates a Blender Object for each and every stud (WARNING: can be slow to import and edit in Blender if there are lots of studs).",
        default=prefs.get("instanceStuds", False)
    )

    resolveNormals = EnumProperty(
        name="Resolve ambiguous normals option",
        description="Some older LDraw parts have faces with ambiguous normals, this specifies what do do with them.",
        default=prefs.get("resolveNormals", "guess"),
        items=(
            ("guess", "Recalculate Normals", "Uses Blender's Recalculate Normals to get a consistent set of normals"),
            ("double", "Two faces back to back", "Two faces are added with their normals pointing in opposite directions"),
        )
    )

    def draw(self, context):
        """Display import options."""

        layout = self.layout
        box = layout.box()
        box.label("Import Options", icon='SCRIPTWIN')
        box.label("LDraw filepath:", icon='FILESEL')
        box.prop(self, "ldrawPath")
        box.prop(self, "importScale")
        #box.label("Parts", icon='MOD_BUILD')
        box.prop(self, "colourScheme", expand=True)
        box.prop(self, "resPrims", expand=True)
        box.prop(self, "smoothParts")
        box.prop(self, "addGaps")
        box.prop(self, "gapsSize")
        box.prop(self, "linkParts")
        box.prop(self, "useUnofficialParts")

        #box.label("Studs", icon='MOD_BUILD')
        box.prop(self, "useLogoStuds")
        box.prop(self, "instanceStuds")

        #box.label("Objects", icon='MOD_BUILD')
        box.prop(self, "positionOnGround")
        box.prop(self, "numberNodes")
        box.prop(self, "flatten")

        box.label("Resolve Ambiguous Normals:", icon='EDIT')
        box.prop(self, "resolveNormals", expand=True)

        #box.label("Additional Options", icon='PREFERENCES')

    def execute(self, context):
        """Start the import process."""

        # Read current preferences from the UI and save them
        ImportLDrawOps.prefs.set("ldrawDirectory",        self.ldrawPath)
        ImportLDrawOps.prefs.set("scale",                 self.importScale)
        ImportLDrawOps.prefs.set("resolution",            self.resPrims)
        ImportLDrawOps.prefs.set("smoothShading",         self.smoothParts)
        ImportLDrawOps.prefs.set("useColourScheme",       self.colourScheme)
        ImportLDrawOps.prefs.set("gaps",                  self.addGaps)
        ImportLDrawOps.prefs.set("gapWidth",              self.gapsSize)
        ImportLDrawOps.prefs.set("linkParts",             self.linkParts)
        ImportLDrawOps.prefs.set("numberNodes",           self.numberNodes)
        ImportLDrawOps.prefs.set("positionObjectOnGroundAtOrigin", self.positionOnGround)
        ImportLDrawOps.prefs.set("flattenHierarchy",      self.flatten)
        ImportLDrawOps.prefs.set("useUnofficialParts",    self.useUnofficialParts)
        ImportLDrawOps.prefs.set("useLogoStuds",          self.useLogoStuds)
        ImportLDrawOps.prefs.set("instanceStuds",         self.instanceStuds)
        ImportLDrawOps.prefs.set("resolveNormals",        self.resolveNormals)
        ImportLDrawOps.prefs.save()

        # Set import options and import
        loadldraw.Options.ldrawDirectory     = self.ldrawPath
        loadldraw.Options.scale              = self.importScale
        loadldraw.Options.useUnofficialParts = self.useUnofficialParts
        loadldraw.Options.resolution         = self.resPrims
        loadldraw.Options.defaultColour      = "4"
        loadldraw.Options.createInstances    = self.linkParts
        loadldraw.Options.useColourScheme    = self.colourScheme
        loadldraw.Options.numberNodes        = self.numberNodes
        loadldraw.Options.removeDoubles      = True
        loadldraw.Options.smoothShading      = self.smoothParts
        loadldraw.Options.edgeSplit          = self.smoothParts     # Edge split is appropriate only if we are smoothing
        loadldraw.Options.gaps               = self.addGaps
        loadldraw.Options.gapWidth           = self.gapsSize
        loadldraw.Options.positionObjectOnGroundAtOrigin = self.positionOnGround
        loadldraw.Options.flattenHierarchy   = self.flatten
        loadldraw.Options.useLogoStuds       = self.useLogoStuds
        loadldraw.Options.logoStudVersion    = "4"
        loadldraw.Options.instanceStuds      = self.instanceStuds
        loadldraw.Options.useLSynthParts     = True
        loadldraw.Options.LSynthDirectory    = os.path.join(os.path.dirname(__file__), "lsynth")
        loadldraw.Options.studLogoDirectory  = os.path.join(os.path.dirname(__file__), "studs")
        loadldraw.Options.resolveAmbiguousNormals = self.resolveNormals

        loadldraw.loadFromFile(self, self.filepath)
        return {'FINISHED'}
