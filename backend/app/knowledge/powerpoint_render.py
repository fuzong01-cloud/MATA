from __future__ import annotations

from pathlib import Path


class PowerPointRenderer:
    """Render complete PPT pages with Microsoft PowerPoint through COM."""

    def __init__(self) -> None:
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise RuntimeError("页面图像导入需要 Windows 和 pywin32") from exc

        self._pythoncom = pythoncom
        self._pythoncom.CoInitialize()
        self._dispatch = win32com.client.DispatchEx

    def render(self, presentation_path: Path, output_dir: Path) -> tuple[dict[int, Path], list[dict]]:
        output_dir.mkdir(parents=True, exist_ok=True)
        application = self._dispatch("PowerPoint.Application")
        application.WindowState = 2
        application.DisplayAlerts = 1
        presentation = None
        rendered: dict[int, Path] = {}
        errors: list[dict] = []
        try:
            presentation = application.Presentations.Open(
                str(presentation_path), ReadOnly=True, Untitled=False, WithWindow=False
            )
            for page_number in range(1, presentation.Slides.Count + 1):
                image_path = output_dir / f"slide-{page_number:04d}.png"
                try:
                    presentation.Slides(page_number).Export(str(image_path), "PNG", 1280, 720)
                    if image_path.is_file() and image_path.stat().st_size:
                        rendered[page_number] = image_path
                    else:
                        errors.append({"slide_number": page_number, "error": "PowerPoint 未生成页面图片"})
                except Exception as exc:
                    errors.append({"slide_number": page_number, "error": str(exc)[:240]})
        finally:
            if presentation is not None:
                try:
                    presentation.Close()
                except Exception:
                    pass
            try:
                application.Quit()
            except Exception:
                pass
        return rendered, errors

    def close(self) -> None:
        self._pythoncom.CoUninitialize()

    def __enter__(self) -> PowerPointRenderer:
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.close()
