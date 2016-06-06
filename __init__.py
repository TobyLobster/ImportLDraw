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

import bpy

from . import importldraw

bl_info = {
    "name": "Import LDraw",
    "description": "Import LDraw models in .mpd .ldr .l3b and .dat formats",
    "author": "Toby Nelson <toby@tnelson.demon.co.uk>",
    "version": (1, 0, 4),
    "blender": (2, 76, 0),
    "location": "File > Import",
    "warning": "",
    "wiki_url": "https://github.com/TobyLobster/ImportLDraw",
    "tracker_url": "https://github.com/TobyLobster/ImportLDraw/issues",
    "category": "Import-Export"
    }


def menuImport(self, context):
    """Import menu listing label."""
    self.layout.operator(importldraw.ImportLDrawOps.bl_idname,
                         text="LDraw (.mpd/.ldr/.l3b/.dat)")


def register():
    """Register Menu Listing."""
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_import.append(menuImport)


def unregister():
    """Unregister Menu Listing."""
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_import.remove(menuImport)


if __name__ == "__main__":
    register()
