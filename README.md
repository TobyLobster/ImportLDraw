# Import LDraw

> Bring your [LEGO](https://www.lego.com/)® creations into [Blender](https://www.blender.org)&trade;: an add-on for importing [LDraw](http://www.ldraw.org)&trade; models and parts.

![Tower Bridge](./images/tower_960.png)

## What is it?

*Import LDraw* loads LEGO models built in LDraw-compatible tools (such as Bricksmith or LeoCAD) or in BrickLink Studio into Blender, ready for you to light, render and animate.

It reads **.mpd**, **.ldr**, **.l3b**, **.dat** and **.io** files, and it's designed to be, in order of priority:

1. **Accurate:** your model should look the way it was built.
2. **Compatible:** it works with files from all the popular LDraw tools.
3. **Fast:** even large models import in seconds.

## Features

### Works where you do

+ Supports Blender 4.0 up to at least Blender 5.1.0. Using an older Blender (2.81 to 3.6)? Version 1.2.3 is still available on the [Releases](https://github.com/TobyLobster/ImportLDraw/releases) page.
+ Runs on **Mac**, **Windows** and **Linux**.
+ Reads **MPD** files and is **Bricksmith** compatible.
+ Opens **BrickLink Studio** models (**.io** files) directly.
+ Understands **LeoCAD** groups and cameras (both perspective and orthographic).
+ Imports **LSynth** bendable parts, such as hoses and cables.

### Looks great

+ **Two styles:** choose a **photorealistic** look rendered with *Cycles*, or a clean **building instructions** look rendered with *EEVEE*.
+ **Physically based materials:** standard brick plastic, transparent, rubber, chrome, metal, pearlescent, glow-in-the-dark, glitter and speckle. There are fabric materials too (cape cloth, canvas, velvet, string and fur) for capes, sails and other cloth parts.
+ **Principled BSDF shader:** every material is built on Blender's Principled BSDF shader.
+ **Printed parts and stickers:** parts that use the LDraw texture mapping extension (`!TEXMAP`: planar, cylindrical and spherical) arrive with their images. Images are found in the *textures* folders of your parts library, or can be embedded in the model file itself (`!DATA`). Embedded images are packed into the .blend file, or can be saved next to the model if you prefer. If you'd rather have the plain versions, untick *Import textures*.
+ **True-to-life colour:** colour spaces are handled correctly, so black parts really do look black.
+ **Direct colours** are supported.
+ **Custom colours:** colours defined inside a model or part file (`!COLOUR`) are respected, following the LDraw rules. A definition applies from where it appears to the end of that file, and to any submodels and parts used after it.
+ **Studio lighting:** the realistic look is lit by an HDR image of a photo studio (*background.exr*). If the image is missing, a similar built-in studio light is used instead.
+ **Light bricks** really do emit light.

### Realistic detail, when you want it

+ **LEGO logo on studs:** add the logo to every stud for close-up shots (this adds extra geometry).
+ **Gaps between bricks:** leave a tiny space between bricks, just like the real thing.
+ **Rounded edges:** bevel the edges of each part, each edge as wide as will fit, so even detailed parts round off cleanly. By default the bevels are baked into each part's shared mesh, which uses far less memory on big models. Untick *Bake bevels* to keep them as Bevel modifiers you can still adjust after importing.
+ **Concave walls:** in the photorealistic look, give each brick very slightly concave walls, for more natural-looking reflections.
+ **Smart smoothing:** curved surfaces are smooth and corners stay sharp, using the Edge Split modifier and sharp edges taken from the LDraw lines.
+ **Accurate normals:** all back face culling (BFC) information is fully parsed.
+ **Transparent background:** optionally render the photorealistic look with a transparent background. The model is still lit by the studio, and its shadows are kept (the ground plane only catches shadows). The instructions look always has a transparent background.

### Easy to work with

+ **Linked duplicates:** parts of the same type and colour share one mesh, and studs can share one mesh too, which saves memory.
+ **Posable minifigs:** optionally parent the parts of each minifig to each other, so rotating an arm also moves the hand with it.
+ **Building steps:** each part remembers the step it was added in (`0 STEP` and `0 ROTSTEP` lines). You can also have the import animate the build:
  + each step's parts appear in turn, with a timeline marker for every step
  + each submodel is built step by step in place, just before the step that uses it (or appears all at once, if you prefer)
  + pieces that LeoCAD hides at a later step disappear at that step
+ **Submodels as collections:** optionally give each submodel its own collection, nested just like the submodels. That makes it easy to show or hide whole sections, or to use them with geometry nodes.
+ **Progress and cancelling:** Import progress is shown in the status bar, Esc cancels it.

![Ghostbusters](./images/ghostbusters_960.png)

## Getting started

### 1. Install the add-on

1. Download the latest version from the [Releases](https://github.com/TobyLobster/ImportLDraw/releases) page. Keep it as a zip file.
2. Open Blender and choose **Edit > Preferences** from the menu.
3. Click the **Add-ons** tab.
4. Then follow the steps for your version of Blender:

**Blender 4.2 and above**

1. Click the down arrow at the top right and choose **Install from Disk...**
2. Find the zip file you downloaded and select it.
3. Find *Import LDraw* in the list of add-ons (search for *LDraw* if you need to) and tick the check box to turn it on.
4. Click the menu button (three horizontal lines) at the bottom left and choose **Save Preferences**, so the add-on is still on the next time you start Blender.

**Blender 4.0 and 4.1**

1. Click the **Install...** button.
2. Find the zip file you downloaded and select it.
3. Find *Import LDraw* in the list of add-ons (search for *LDraw* if you need to) and tick the check box to turn it on.
4. Click **Save Preferences**, so the add-on is still on the next time you start Blender.

### 2. Get the LDraw parts library

*Import LDraw* needs the LDraw parts library to know what each part looks like.

1. Download the latest complete [LDraw Parts Library](https://library.ldraw.org/updates?latest).
2. Either unzip it into a folder (for example, one called `ldraw`), or simply keep it zipped. *Import LDraw* can read parts straight from *complete.zip*.
3. **Optional:** for parts that aren't in the official library yet, download the unofficial parts too. Unzip them into `ldraw/unofficial/`, or put the zipped *ldrawunf.zip* in your `ldraw` folder or next to *complete.zip*.

### 3. Import your first model

1. In Blender, choose **File > Import > LDraw (.io/.mpd/.ldr/.l3b/.dat)**.
   In Blender 4.1 and above, you can also drag an LDraw file from Finder or File Explorer straight onto the 3D Viewport or Outliner. The import options will appear in a pop-up.
2. In the **Import Options** panel on the right hand side, the first option is the LDraw Parts Library directory. Enter the full path to your `ldraw` folder. If you kept the library zipped, enter the folder containing *complete.zip*, or the path of the zip file itself.
3. Choose a model to import. Your library location is saved, so you only need to set it once.

That's it. Enjoy building!

![Tugboat](./images/tugboat_960.png)

## History

*Import LDraw* is written by Toby Nelson (tobymnelson@gmail.com), and was first created in May 2016.

It was inspired by, and originally based on, code from [LDR-Importer](https://github.com/le717/LDR-Importer), but it has since been completely rewritten.

![Marina Bay Sands](./images/marina_bay_sands_960.png)

## License

*Import LDraw* is licensed under the [GPLv2](http://www.gnu.org/licenses/gpl-2.0.html) or any later version.

## Thanks

A big thank you to [BertVanRaemdonck](https://github.com/BertVanRaemdonck) for the 'concave walls' feature, and for lots of helpful feedback and suggestions.

## Related projects

<a href="https://www.blender.org/"><img align="left" src="./images/logos/blender-plain.png" alt="Blender logo" style="margin: 0px 10px 0px 0px;"/></a>

**Blender**&trade; is the free and open source 3D creation suite.<br clear=left>

<a href="http://www.ldraw.org/"><img align="left" src="./images/logos/Official_LDraw_Logo.png" alt="LDraw logo" style="margin: 0px 10px 0px 0px;"/></a>

**LDraw**&trade; is an open standard for LEGO CAD programs, letting you create virtual LEGO models and scenes. You can use it to record models you've built for real, create building instructions just like LEGO's, render photorealistic 3D images of your virtual models, and even make animations. Unlike with real bricks, you're never short of parts or colours. In LDraw, nothing is impossible.

LDraw&trade; is a trademark owned and licensed by the Estate of James Jessiman. This add-on is not developed or endorsed by the creators of The LDraw System of Tools.<br clear=left>

<a href="http://bricksmith.sourceforge.net"><img align="left" src="./images/logos/BricksmithIcon.png" alt="Bricksmith logo" style="margin: 0px 10px 0px 0px;"/></a>

**Bricksmith** lets you build virtual LEGO models and create instructions for them on your Mac.<br clear=left>

<a href="https://deeice.github.io/lsynth/"><img align="left" src="./images/logos/LSynthExample.png" alt="LSynth example" style="margin: 0px 10px 0px 0px;"/></a>

**LSynth** generates bendable parts, such as hoses and cables, for LDraw files.<br clear=left>

<a href="https://www.lego.com/"><img align="left" src="./images/logos/lego.jpg" alt="LEGO logo" style="margin: 0px 10px 0px 0px;"/></a>

**LEGO**® is a registered trademark of the LEGO Group.<br clear=left>
