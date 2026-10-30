"""3D-view overlays: Qt-drawn value labels, ring-center spheres, HOMA colors.

VTK text supports only three font families and no underline, so each label is
drawn with QPainter (any installed font, bold/italic/underline) and shown as a
2D image anchored to the ring center in world coordinates.  Labels stay on top
of the molecule, like the host's own atom labels.
"""

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter
from vtkmodules.util.numpy_support import numpy_to_vtk
from vtkmodules.vtkCommonDataModel import vtkImageData
from vtkmodules.vtkRenderingCore import vtkActor2D, vtkCoordinate, vtkImageMapper

PAD = 3
PX_PER_PT = 96 / 72
SCALARS = "HOMA"


def colormap(name: str):
    """The named matplotlib colormap, as pyvista resolves it."""
    from pyvista.plotting.colors import get_cmap_safe

    return get_cmap_safe(name)


def value_color(value: float, settings: dict) -> str:
    """Hex color of ``value`` on the gradient; values outside the range clip."""
    lo, hi = settings["range_min"], settings["range_max"]
    t = min(max((value - lo) / (hi - lo), 0.0), 1.0)
    r, g, b = colormap(settings["colormap"])(t)[:3]
    return "#{:02x}{:02x}{:02x}".format(*(round(c * 255) for c in (r, g, b)))


def label_font(settings: dict, scale: float = 1.0) -> QFont:
    font = QFont(settings["font_family"])
    font.setPixelSize(max(1, round(settings["font_size"] * PX_PER_PT * scale)))
    font.setBold(settings["bold"])
    font.setItalic(settings["italic"])
    font.setUnderline(settings["underline"])
    return font


def render_label(text: str, color: str, settings: dict, scale: float = 1.0):
    """RGBA pixels of ``text``, bottom row first (VTK's image order)."""
    font = label_font(settings, scale)
    metrics = QFontMetrics(font)
    width = metrics.horizontalAdvance(text) + 2 * PAD
    if font.italic():
        width += metrics.height() // 4  # the slant leans past the advance
    height = metrics.height() + 2 * PAD
    image = QImage(width, height, QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setFont(font)
    painter.setPen(QColor(color))
    painter.drawText(PAD, PAD + metrics.ascent(), text)
    painter.end()
    rows = np.frombuffer(image.constBits(), np.uint8).reshape(
        height, image.bytesPerLine() // 4, 4
    )
    return np.ascontiguousarray(rows[::-1, :width])


def label_actor(position, pixels) -> vtkActor2D:
    """A 2D actor showing ``pixels`` centered on the world point ``position``."""
    height, width = pixels.shape[:2]
    data = vtkImageData()
    data.SetDimensions(width, height, 1)
    data.GetPointData().SetScalars(numpy_to_vtk(pixels.reshape(-1, 4), deep=True))
    mapper = vtkImageMapper()
    mapper.SetInputData(data)
    mapper.SetColorWindow(255)
    mapper.SetColorLevel(127.5)
    actor = vtkActor2D()
    actor.SetMapper(mapper)
    anchor = vtkCoordinate()
    anchor.SetCoordinateSystemToWorld()
    anchor.SetValue(*position)
    coord = actor.GetPositionCoordinate()
    coord.SetCoordinateSystemToDisplay()
    coord.SetReferenceCoordinate(anchor)
    coord.SetValue(-width / 2, -height / 2)
    actor.PickableOff()
    actor._homa_anchor = anchor  # keep the reference coordinate alive
    return actor


def sphere_mesh(centers, radius: float, values=None):
    """One mesh holding a sphere at each ring center, carrying its HOMA value."""
    import pyvista as pv

    spheres = []
    for i, center in enumerate(centers):
        s = pv.Sphere(
            radius=radius, center=center, theta_resolution=24, phi_resolution=24
        )
        if values is not None:
            s.point_data[SCALARS] = np.full(s.n_points, values[i], dtype=float)
        spheres.append(s)
    mesh = spheres[0]
    for s in spheres[1:]:
        mesh = mesh.merge(s)
    return mesh


def legend_mesh(position, settings: dict):
    """An invisible two-point mesh spanning the range, to carry the scalar bar."""
    import pyvista as pv

    mesh = pv.PolyData(np.array([position, position], dtype=float))
    mesh.point_data[SCALARS] = np.array(
        [settings["range_min"], settings["range_max"]], dtype=float
    )
    return mesh


def legend_args(settings: dict) -> dict:
    vertical = settings["legend_vertical"]
    args = {
        "title": settings["legend_title"],
        "vertical": vertical,
        "n_labels": settings["legend_labels"],
        "fmt": f"%.{settings['decimals']}f",
        "title_font_size": settings["legend_font_size"] + 2,
        "label_font_size": settings["legend_font_size"],
        "color": settings["legend_color"],
        "italic": False,
        "bold": False,
    }
    if vertical:
        args.update(position_x=0.88, position_y=0.25, width=0.08, height=0.5)
    else:
        args.update(position_x=0.3, position_y=0.04, width=0.4, height=0.08)
    return args
