#!/usr/bin/python3
"""Grid of pose renders with labels -> pose_sheet.png"""
import cairo, gi, warnings
warnings.filterwarnings("ignore")
gi.require_version("Gdk", "4.0"); gi.require_version("GdkPixbuf", "2.0"); gi.require_version("PangoCairo", "1.0")
from gi.repository import GdkPixbuf, Gdk, Pango, PangoCairo
names = ["salam_wave", "counting_tasbih", "dua", "walking", "thinking", "sleepy"]
pbs = [GdkPixbuf.Pixbuf.new_from_file(f"pose_{n}.png") for n in names]
w, h, cols = pbs[0].get_width(), pbs[0].get_height(), 3
S = cairo.ImageSurface(cairo.FORMAT_RGB24, w * cols, (h + 40) * 2); cr = cairo.Context(S)
cr.set_source_rgb(0.86, 0.87, 0.91); cr.paint()
for i, (n, pb) in enumerate(zip(names, pbs)):
    x, y = (i % cols) * w, (i // cols) * (h + 40)
    Gdk.cairo_set_source_pixbuf(cr, pb, x, y + 40); cr.paint()
    l = PangoCairo.create_layout(cr); l.set_font_description(Pango.FontDescription("Ubuntu Sans Medium 18"))
    l.set_text(n.replace("_", " ").capitalize(), -1); cr.set_source_rgb(0.2, 0.2, 0.3); cr.move_to(x + 20, y + 8); PangoCairo.show_layout(cr, l)
S.write_to_png("pose_sheet.png"); print("pose_sheet.png")
