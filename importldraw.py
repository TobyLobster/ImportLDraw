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
import traceback
import bpy
from bpy.props import (StringProperty,
                       FloatProperty,
                       IntProperty,
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
realScale          = 0.0002
resolution         = "Standard"
smoothShading      = True
useLook            = "normal"
useColourScheme    = "lgeo"
gaps               = True
realGapWidth       = 0.0001
createInstances    = True
numberNodes        = True
positionObjectOnGroundAtOrigin = True
flattenHierarchy   = False
useUnofficialParts = True
useLogoStuds       = False
instanceStuds      = False
curvedWalls        = True
(etc)
"""


class Preferences():
    """Import LDraw - Preferences"""
    __sectionName   = 'importldraw'

    def __init__(self):
        self.__ldPath        = None
        self.__prefsPath     = os.path.dirname(__file__)
        self.__prefsFilepath = os.path.join(self.__prefsPath, "ImportLDrawPreferences.ini")
        self.__config        = configparser.RawConfigParser()
        self.__prefsRead     = self.__config.read(self.__prefsFilepath)
        if self.__prefsRead and not self.__config.has_section(Preferences.__sectionName):
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
        except Exception as e:
            # Fail gracefully
            loadldraw.debugPrint("WARNING: Could not save preferences. {0}".format(e))
            return False


def indentedRow(layout, enabled=True):
    """A slightly indented row in the import options, for a setting that goes with the one above it"""
    row = layout.row()
    row.separator()
    row.enabled = enabled
    return row


class ImportLDrawOps(bpy.types.Operator, ImportHelper):
    """Import LDraw - Import Operator."""

    bl_idname       = "import_scene.importldraw"
    bl_description  = "Import LDraw models (.io/.mpd/.ldr/.l3b/.dat)"
    bl_label        = "Import LDraw Models"
    bl_space_type   = "PROPERTIES"
    bl_region_type  = "WINDOW"
    bl_options      = {'REGISTER', 'UNDO', 'PRESET'}

    # Instance the preferences system
    prefs = Preferences()

    # File type filter in file browser
    filename_ext = ".ldr"
    filter_glob: StringProperty(
        default="*.io;*.mpd;*.ldr;*.l3b;*.dat",
        options={'HIDDEN'}
    )

    ldrawPath: StringProperty(
        name="",
        description="Full filepath to the LDraw Parts Library folder (download from https://library.ldraw.org). It can also be the zipped library, complete.zip, or a folder containing it. An 'ldrawunf.zip' of unofficial parts is used too if it is next to complete.zip",
        default=prefs.get("ldrawDirectory", loadldraw.Configure.findDefaultLDrawDirectory())
    )

    realScale: FloatProperty(
        name="Scale",
        description="Sets a scale for the model (1.0 = real life scale)",
        default=prefs.get("realScale", 1.0)
    )

    resPrims: EnumProperty(
        name="Resolution of part primitives",
        description="Resolution of part primitives, ie. how much geometry they have",
        default=prefs.get("resolution", "Standard"),
        items=(
            ("Standard", "Standard",                   "Import using standard resolution primitives."),
            ("High",     "High resolution",            "Import using high resolution primitives."),
            ("Low",      "Low resolution",             "Import using low resolution primitives.")
        )
    )

    smoothParts: BoolProperty(
        name="Smooth faces and edge-split",
        description="Smooth faces and add an edge-split modifier",
        default=prefs.get("smoothShading", True)
    )

    look: EnumProperty(
        name="Overall Look",
        description="Realism or Schematic look",
        default=prefs.get("useLook", "normal"),
        items=(
            ("normal", "Realistic look", "Render to look realistic."),
            ("instructions", "Instructions look", "Render to look like the instruction book pictures."),
        )
    )

    colourScheme: EnumProperty(
        name="Colour scheme options",
        description="Colour scheme options",
        default=prefs.get("useColourScheme", "lgeo"),
        items=(
            ("lgeo", "Realistic colours", "Uses the LGEO colour scheme for realistic colours."),
            ("ldraw", "Original LDraw colours", "Uses the standard LDraw colour scheme. Looks good with the Instructions Look."),
            ("alt", "Alternate LDraw colours", "Uses the alternate LDraw colour scheme. Looks good with the Instructions Look."),
        )
    )

    defaultColour: StringProperty(
        name="Default Colour on Import:",
        description="Default colour used on Import. Default: 4 (Red)",
        default=prefs.get("defaultColour", "4")
    )

    addGaps: BoolProperty(
        name="Add space between each part:",
        description="Add a small space between each part",
        default=prefs.get("gaps", False)
    )

    gapWidthMM: FloatProperty(
        name="Space",
        description="Amount of space between each part (default 0.1mm)",
        default=1000 * prefs.get("realGapWidth", 0.0001)
    )

    curvedWalls: BoolProperty(
        name="Use curved wall normals",
        description="Makes surfaces look slightly concave, for interesting reflections",
        default=prefs.get("curvedWalls", True)
    )

    importCameras: BoolProperty(
        name="Import cameras",
        description="Import camera definitions (from models authored in LeoCAD)",
        default=prefs.get("importCameras", True)
    )

    linkParts: BoolProperty(
        name="Link identical parts",
        description="Identical parts (of the same type and colour) share the same mesh",
        default=prefs.get("linkParts", True)
    )

    numberNodes: BoolProperty(
        name="Number each object",
        description="Each object has a five digit prefix eg. 00001_car. This keeps the list in it's proper order",
        default=prefs.get("numberNodes", True)
    )

    positionOnGround: BoolProperty(
        name="Put model on ground at origin",
        description="The object is centred at the origin, and on the ground plane",
        default=prefs.get("positionObjectOnGroundAtOrigin", True)
    )

    flatten: BoolProperty(
        name="Flatten tree",
        description="In Scene Outliner, all parts are placed directly below the root - there's no tree of submodels",
        default=prefs.get("flattenHierarchy", False)
    )

    submodelCollections: BoolProperty(
        name="Submodels as collections",
        description="Each submodel also gets its own collection, nested in the same way as the submodels, so you can hide or show a whole submodel, or use it in geometry nodes. (In the instructions look, bricks are also in the 'Solid' and 'Transparent' collections used for rendering, so hiding a submodel collection hides it in the viewport but not in the render)",
        default=prefs.get("submodelCollections", False)
    )

    animateSteps: BoolProperty(
        name="Animate building steps",
        description="Animate building the model step by step, from its building steps ('0 STEP' lines). Each step's parts appear in turn (a submodel appears all at once). The timeline has a marker for each step",
        default=prefs.get("animateSteps", False)
    )

    framesPerStep: IntProperty(
        name="Frames per step",
        description="How many frames each building step takes in the animation",
        default=prefs.get("framesPerStep", 1),
        min=1,
        max=10000
    )

    expandSubmodels: BoolProperty(
        name="Build submodels step by step",
        description="In the animation, build each submodel step by step too (where it goes in the model), before the step that uses it. Otherwise a submodel appears all at once",
        default=prefs.get("expandSubmodels", True)
    )

    minifigHierarchy: BoolProperty(
        name="Parent Minifigs",
        description="Add a parent/child hierarchy (tree) for Minifigs",
        default=prefs.get("minifigHierarchy", True)
    )

    useUnofficialParts: BoolProperty(
        name="Include unofficial parts",
        description="Additionally searches for parts in the <ldraw-dir>/unofficial/ directory",
        default=prefs.get("useUnofficialParts", True)
    )

    useTextures: BoolProperty(
        name="Import textures",
        description="Apply texture images to printed parts and stickers that use !TEXMAP (otherwise their untextured fallback shapes are used)",
        default=prefs.get("useTextures", True)
    )

    packEmbeddedImages: BoolProperty(
        name="Pack embedded images",
        description="Texture images embedded in the model file are packed into the .blend file. Otherwise they are saved as files next to the model",
        default=prefs.get("packEmbeddedImages", True)
    )

    useLogoStuds: BoolProperty(
        name="Show 'LEGO' logo on studs",
        description="Shows the LEGO logo on each stud (at the expense of some extra geometry and import time)",
        default=prefs.get("useLogoStuds", False)
    )

    instanceStuds: BoolProperty(
        name="Make individual studs",
        description="Creates a Blender Object for each and every stud (WARNING: can be slow to import and edit in Blender if there are lots of studs)",
        default=prefs.get("instanceStuds", False)
    )

    resolveNormals: EnumProperty(
        name="Resolve ambiguous normals option",
        description="Some older LDraw parts have faces with ambiguous normals, this specifies what do do with them",
        default=prefs.get("resolveNormals", "guess"),
        items=(
            ("guess", "Recalculate Normals", "Uses Blender's Recalculate Normals to get a consistent set of normals."),
            ("double", "Two faces back to back", "Two faces are added with their normals pointing in opposite directions."),
        )
    )

    bevelEdges: BoolProperty(
        name="Bevel edges",
        description="Adds a Bevel modifier for rounding off sharp edges",
        default=prefs.get("bevelEdges", True)
    )

    bevelWidth: FloatProperty(
        name="Bevel Width",
        description="Width of the bevelled edges",
        default=prefs.get("bevelWidth", 0.5)
    )

    bakeBevels: BoolProperty(
        name="Bake bevels",
        description="Applies the bevels (and the edge splitting used for smoothing) to each part's mesh, which all parts of that kind share, instead of adding modifiers to every part. This uses far less memory and time for big models, but the bevels can't be adjusted after import. (Only used when bevelling edges, so not with the Instructions Look)",
        default=prefs.get("bakeBevels", True)
    )

    addEnvironment: BoolProperty(
        name="Add Environment",
        description="Adds a ground plane and environment texture (for realistic look only)",
        default=prefs.get("addEnvironment", True)
    )

    transparentBackground: BoolProperty(
        name="Transparent background",
        description="Renders the Realistic Look with a transparent background, e.g. to put the picture on a web page or over another picture. The environment still lights the model, and the ground plane only catches the model's shadows. (The Instructions Look always has a transparent background)",
        default=prefs.get("transparentBackground", False)
    )

    positionCamera: BoolProperty(
        name="Position the camera",
        description="Position the camera to show the whole model",
        default=prefs.get("positionCamera", True)
    )

    cameraBorderPercentage: FloatProperty(
        name="Camera Border %",
        description="When positioning the camera, include a (percentage) border leeway around the model in the rendered image",
        default=prefs.get("cameraBorderPercentage", 5.0)
    )

    def invoke(self, context, event):
        # A file dropped on the 3D Viewport or the Outliner (see ImportLDrawFileHandler): the file is already chosen,
        # so the import options are shown in a pop-up instead of the file browser
        if self.properties.is_property_set("filepath"):
            title = os.path.basename(self.filepath)
            try:
                return context.window_manager.invoke_props_dialog(self, width=400, title=title, confirm_text="Import")
            except TypeError:
                # (Blender 4.1 has no title or confirm_text)
                return context.window_manager.invoke_props_dialog(self, width=400)
        return ImportHelper.invoke(self, context, event)

    def draw(self, context):
        """Display import options."""

        # The file browser's side panel is narrow, and an add-on can't make it wider. So the settings are in
        # sections with headings, and each takes the full width (no column of labels beside them).
        layout = self.layout
        layout.use_property_split = False

        box = layout.box()
        box.label(text="LDraw parts library", icon='FILEBROWSER')
        box.prop(self, "ldrawPath", text="")
        box.prop(self, "useUnofficialParts")

        box = layout.box()
        box.label(text="Look", icon='SHADING_RENDERED')
        box.column(align=True).prop(self, "look", expand=True)
        box.label(text="Colours:")
        box.column(align=True).prop(self, "colourScheme", expand=True)
        row = box.row()
        row.label(text="Default colour")
        row.prop(self, "defaultColour", text="")
        box.prop(self, "addEnvironment")
        row = box.row()
        row.enabled = self.look != "instructions"
        row.prop(self, "transparentBackground")
        box.prop(self, "positionCamera")
        indentedRow(box, self.positionCamera).prop(self, "cameraBorderPercentage", text="Camera border %")

        box = layout.box()
        box.label(text="Parts", icon='MESH_CUBE')
        box.prop(self, "realScale", text="Scale")
        box.label(text="Primitives:")
        box.column(align=True).prop(self, "resPrims", expand=True)
        box.prop(self, "smoothParts", text="Smooth faces")
        box.prop(self, "bevelEdges")
        indentedRow(box, self.bevelEdges).prop(self, "bevelWidth", text="Bevel width")
        indentedRow(box, self.bevelEdges and self.look != "instructions").prop(self, "bakeBevels")
        box.prop(self, "addGaps", text="Gaps between parts")
        indentedRow(box, self.addGaps).prop(self, "gapWidthMM", text="Gap width (mm)")
        box.prop(self, "curvedWalls", text="Curved walls")
        box.prop(self, "useLogoStuds", text="LEGO logo on studs")
        box.prop(self, "instanceStuds")
        box.prop(self, "useTextures")
        indentedRow(box, self.useTextures).prop(self, "packEmbeddedImages")
        box.prop(self, "linkParts")

        box = layout.box()
        box.label(text="Objects", icon='OUTLINER')
        box.prop(self, "positionOnGround", text="Place on ground at origin")
        box.prop(self, "numberNodes")
        box.prop(self, "flatten")
        indentedRow(box, not self.flatten).prop(self, "submodelCollections")
        box.prop(self, "minifigHierarchy", text="Parent minifigs")
        box.prop(self, "importCameras")

        box = layout.box()
        box.label(text="Building steps", icon='TIME')
        box.prop(self, "animateSteps")
        indentedRow(box, self.animateSteps).prop(self, "framesPerStep")
        indentedRow(box, self.animateSteps).prop(self, "expandSubmodels")

        box = layout.box()
        box.label(text="Ambiguous normals", icon='ORIENTATION_NORMAL')
        box.column(align=True).prop(self, "resolveNormals", expand=True)

    def execute(self, context):
        """Start the import process."""

        # Read current preferences from the UI and save them
        ImportLDrawOps.prefs.set("ldrawDirectory",        self.ldrawPath)
        ImportLDrawOps.prefs.set("realScale",             self.realScale)
        ImportLDrawOps.prefs.set("resolution",            self.resPrims)
        ImportLDrawOps.prefs.set("smoothShading",         self.smoothParts)
        ImportLDrawOps.prefs.set("bevelEdges",            self.bevelEdges)
        ImportLDrawOps.prefs.set("bevelWidth",            self.bevelWidth)
        ImportLDrawOps.prefs.set("bakeBevels",            self.bakeBevels)
        ImportLDrawOps.prefs.set("useLook",               self.look)
        ImportLDrawOps.prefs.set("useColourScheme",       self.colourScheme)
        ImportLDrawOps.prefs.set("defaultColour",         self.defaultColour)
        ImportLDrawOps.prefs.set("gaps",                  self.addGaps)
        ImportLDrawOps.prefs.set("realGapWidth",          self.gapWidthMM / 1000)
        ImportLDrawOps.prefs.set("curvedWalls",           self.curvedWalls)
        ImportLDrawOps.prefs.set("importCameras",         self.importCameras)
        ImportLDrawOps.prefs.set("linkParts",             self.linkParts)
        ImportLDrawOps.prefs.set("numberNodes",           self.numberNodes)
        ImportLDrawOps.prefs.set("positionObjectOnGroundAtOrigin", self.positionOnGround)
        ImportLDrawOps.prefs.set("flattenHierarchy",      self.flatten)
        ImportLDrawOps.prefs.set("submodelCollections",   self.submodelCollections)
        ImportLDrawOps.prefs.set("minifigHierarchy",      self.minifigHierarchy)
        ImportLDrawOps.prefs.set("animateSteps",          self.animateSteps)
        ImportLDrawOps.prefs.set("framesPerStep",         self.framesPerStep)
        ImportLDrawOps.prefs.set("expandSubmodels",       self.expandSubmodels)
        ImportLDrawOps.prefs.set("useUnofficialParts",    self.useUnofficialParts)
        ImportLDrawOps.prefs.set("useTextures",           self.useTextures)
        ImportLDrawOps.prefs.set("packEmbeddedImages",    self.packEmbeddedImages)
        ImportLDrawOps.prefs.set("useLogoStuds",          self.useLogoStuds)
        ImportLDrawOps.prefs.set("instanceStuds",         self.instanceStuds)
        ImportLDrawOps.prefs.set("resolveNormals",        self.resolveNormals)
        ImportLDrawOps.prefs.set("addEnvironment",        self.addEnvironment)
        ImportLDrawOps.prefs.set("positionCamera",        self.positionCamera)
        ImportLDrawOps.prefs.set("transparentBackground", self.transparentBackground)
        ImportLDrawOps.prefs.set("cameraBorderPercentage",self.cameraBorderPercentage)
        ImportLDrawOps.prefs.save()

        # Set import options and import
        loadldraw.Options.ldrawDirectory             = self.ldrawPath
        loadldraw.Options.realScale                  = self.realScale
        loadldraw.Options.useUnofficialParts         = self.useUnofficialParts
        loadldraw.Options.resolution                 = self.resPrims
        loadldraw.Options.defaultColour              = self.defaultColour
        loadldraw.Options.createInstances            = self.linkParts
        loadldraw.Options.instructionsLook           = self.look == "instructions"
        loadldraw.Options.useColourScheme            = self.colourScheme
        loadldraw.Options.numberNodes                = self.numberNodes
        loadldraw.Options.removeDoubles              = True
        loadldraw.Options.smoothShading              = self.smoothParts
        loadldraw.Options.edgeSplit                  = self.smoothParts     # Edge split is appropriate only if we are smoothing
        loadldraw.Options.gaps                       = self.addGaps
        loadldraw.Options.realGapWidth               = self.gapWidthMM / 1000
        loadldraw.Options.curvedWalls                = self.curvedWalls
        loadldraw.Options.importCameras              = self.importCameras
        loadldraw.Options.positionObjectOnGroundAtOrigin = self.positionOnGround
        loadldraw.Options.flattenHierarchy           = self.flatten
        loadldraw.Options.submodelCollections        = self.submodelCollections
        loadldraw.Options.minifigHierarchy           = self.minifigHierarchy
        loadldraw.Options.animateSteps               = self.animateSteps
        loadldraw.Options.framesPerStep              = self.framesPerStep
        loadldraw.Options.expandSubmodels            = self.expandSubmodels
        loadldraw.Options.useTextures                = self.useTextures
        loadldraw.Options.packEmbeddedImages         = self.packEmbeddedImages
        loadldraw.Options.useLogoStuds               = self.useLogoStuds
        loadldraw.Options.logoStudVersion            = "4"
        loadldraw.Options.instanceStuds              = self.instanceStuds
        loadldraw.Options.useLSynthParts             = True
        loadldraw.Options.LSynthDirectory            = os.path.join(os.path.dirname(__file__), "lsynth")
        loadldraw.Options.studLogoDirectory          = os.path.join(os.path.dirname(__file__), "studs")
        loadldraw.Options.resolveAmbiguousNormals    = self.resolveNormals
        loadldraw.Options.overwriteExistingMaterials = False
        loadldraw.Options.overwriteExistingMeshes    = False
        loadldraw.Options.addBevelModifier           = self.bevelEdges and not loadldraw.Options.instructionsLook
        loadldraw.Options.bevelWidth                 = self.bevelWidth
        loadldraw.Options.bakeBevels                 = self.bakeBevels
        loadldraw.Options.addWorldEnvironmentTexture = self.addEnvironment
        loadldraw.Options.addGroundPlane             = self.addEnvironment
        loadldraw.Options.transparentBackground      = self.transparentBackground
        loadldraw.Options.positionCamera             = self.positionCamera
        loadldraw.Options.cameraBorderPercent        = self.cameraBorderPercentage / 100.0

        # From the File menu, the import goes a step at a time (see ImportLDrawSteps), so Blender stays responsive,
        # shows how far the import has got, and Esc cancels it. From a script, or when the import is redone with
        # different settings ('Adjust Last Operation'), it is done all at once.
        if (self.options.is_invoke and not (self.options.is_repeat or self.options.is_repeat_last) and
                context.window is not None and not bpy.app.background):
            try:
                result = bpy.ops.import_scene.importldraw_steps('INVOKE_DEFAULT', filepath=self.filepath)
            except RuntimeError:
                result = None
            if result is not None and 'RUNNING_MODAL' in result:
                return {'FINISHED'}

        if loadldraw.loadFromFile(self, self.filepath) is None:
            return {'CANCELLED'}
        return {'FINISHED'}


# Drag and drop: LDraw files dropped on the 3D Viewport or the Outliner are imported (Blender 4.1 and above)
if hasattr(bpy.types, "FileHandler"):
    class ImportLDrawFileHandler(bpy.types.FileHandler):
        bl_idname          = "IO_FH_importldraw"
        bl_label           = "LDraw"
        bl_import_operator = "import_scene.importldraw"
        bl_file_extensions = ".ldr;.mpd;.dat;.l3b;.io"

        @classmethod
        def poll_drop(cls, context):
            return context.area is not None and context.area.type in ('VIEW_3D', 'OUTLINER')
else:
    ImportLDrawFileHandler = None


class ImportLDrawSteps(bpy.types.Operator):
    """
    Imports an LDraw file a step at a time (see loadldraw.ImportTask): Blender carries on between steps, so it stays
    responsive (on macOS it would otherwise show the spinning cursor). The status bar shows how far the import has
    got, and Esc cancels it. Started by ImportLDrawOps, once the import options are set.
    """

    bl_idname       = "import_scene.importldraw_steps"
    bl_label        = "Import LDraw"
    bl_options      = {'UNDO', 'INTERNAL'}

    filepath: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    # How long each step runs before Blender carries on (handling input, redrawing) for a moment
    stepSeconds = 0.1

    # Events let through to Blender while importing (all other input is ignored, so nothing changes the scene
    # halfway through)
    passThrough = {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'TIMER_REPORT', 'TIMERREGION', 'TIMER_JOBS',
                   'TIMER_AUTOSAVE', 'WINDOW_DEACTIVATE', 'NONE'}

    def invoke(self, context, event):
        loadldraw.Progress.useCursor = False
        self.task = loadldraw.ImportTask(self, self.filepath)
        self.timer = context.window_manager.event_timer_add(0.02, window=context.window)
        context.window_manager.modal_handler_add(self)
        self.showStatus(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS' and loadldraw.Progress.canCancel():
            self.task.cancel()
            self.report({'WARNING'}, "Import cancelled")
            return self.stop(context, {'CANCELLED'})

        if event.type == 'TIMER':
            try:
                finished = self.task.step(self.stepSeconds)
            except Exception as error:
                traceback.print_exc()
                self.report({'ERROR'}, "The import failed: {0}".format(error))
                return self.stop(context, {'CANCELLED'})
            if finished:
                return self.stop(context, {'FINISHED'} if self.task.result is not None else {'CANCELLED'})
            self.showStatus(context)
            return {'RUNNING_MODAL'}

        if event.type in self.passThrough:
            return {'PASS_THROUGH'}
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        """Blender stops the import (e.g. when a file is opened, or Blender quits)"""
        self.task.cancel()
        self.stop(context, None)

    def stop(self, context, result):
        context.window_manager.event_timer_remove(self.timer)
        if context.workspace is not None:
            context.workspace.status_text_set(None)
        loadldraw.Progress.useCursor = True
        return result

    def showStatus(self, context):
        text = "Importing LDraw: " + loadldraw.Progress.statusText()
        if loadldraw.Progress.canCancel():
            text += "        Esc to cancel"
        if context.workspace is not None:
            context.workspace.status_text_set(text)
