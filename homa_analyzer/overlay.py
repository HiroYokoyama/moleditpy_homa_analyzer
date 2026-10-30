"""3D-view overlays: Qt-drawn value labels and ring-center spheres.

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


def label_font(settings: dict, scale: float = 1.0) -> QFont:
    font = QFont(settings["font_family"])
    font.setPixelSize(max(1, round(settings["font_size"] * PX_PER_PT * scale)))
    font.setBold(settings["bold"])
    font.setItalic(settings["italic"])
    font.setUnderline(settings["underline"])
    return font


def render_label(text: str, settings: dict, scale: float = 1.0) -> np.ndarray:
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
    painter.setPen(QColor(settings["label_color"]))
    painter.drawText(PAD, PAD + metrics.ascent(), text)
    painter.end()
    rows = np.frombuffer(image.constBits(), np.uint8).reshape(
        height, image.bytesPerLine() // 4, 4
    )
    return np.ascontiguousarray(rows[::-1, :width])


def label_actor(position, pixels: np.ndarray) -> vtkActor2D:
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


def sphere_mesh(centers, radius: float):
    """One mesh holding a sphere at each ring center."""
    import pyvista as pv

    spheres = [
        pv.Sphere(radius=radius, center=c, theta_resolution=24, phi_resolution=24)
        for c in centers
    ]
    mesh = spheres[0]
    for s in spheres[1:]:
        mesh = mesh.merge(s)
    return mesh
