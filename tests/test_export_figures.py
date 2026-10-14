"""Figure extraction, source protection and one small real notebook execution."""

import base64
import builtins
import hashlib
import json
import struct
import zlib
from pathlib import Path

import nbformat
import pytest

import sensor_data as sd
from scripts import export_figures as export


def png(index):
    """A valid one-pixel fixture with a distinct color for output-order checks."""

    def chunk(kind, content):
        payload = kind + content
        return struct.pack("!I", len(content)) + payload + struct.pack("!I", zlib.crc32(payload))

    return (
        export.PNG_SIGNATURE
        + chunk(b"IHDR", struct.pack("!2I5B", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes([0, index, 0, 0, 255])))
        + chunk(b"IEND", b"")
    )


def rendered_notebook(count=6):
    notebook = nbformat.v4.new_notebook()
    for index in range(count):
        notebook.cells.append(
            nbformat.v4.new_code_cell(
                outputs=[
                    nbformat.v4.new_output("stream", name="stdout", text="synthetic private text"),
                    nbformat.v4.new_output(
                        "display_data",
                        data={"image/png": base64.b64encode(png(index)).decode("ascii")},
                    ),
                ]
            )
        )
    return notebook


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    (root / "notebooks").mkdir(parents=True)
    (root / "data").mkdir()
    notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("print('synthetic')")])
    nbformat.write(notebook, root / "notebooks" / "explore_data.ipynb")
    (root / "sensor_data.py").write_text('"""Synthetic analysis fixture."""\n', encoding="utf-8")
    for filename in sd.CSV_FILES.values():
        (root / "data" / filename).write_text("value\n1\n", encoding="utf-8")
    (root / "data" / "RECORDING_PROVENANCE.json").write_text("{}\n", encoding="utf-8")
    return root


@pytest.fixture
def fake_execution(monkeypatch):
    monkeypatch.setattr(export, "_execute_notebook", lambda source, root: rendered_notebook())


def source_bytes(checkout):
    return {
        path.relative_to(checkout): path.read_bytes()
        for path in checkout.rglob("*")
        if path.is_file()
    }


def test_png_extraction_preserves_cell_and_output_order_and_ignores_text():
    notebook = rendered_notebook()
    notebook.cells[0].outputs.extend(notebook.cells.pop(1).outputs)
    encoded = notebook.cells[0].outputs[1].data["image/png"]
    notebook.cells[0].outputs[1].data["image/png"] = [encoded[:16] + "\n", encoded[16:]]
    assert export.extract_pngs(notebook) == [png(index) for index in range(6)]


@pytest.mark.parametrize("count", [0, 5, 7])
def test_png_count_must_match_the_six_documented_figures(count):
    with pytest.raises(ValueError, match="Expected six"):
        export.extract_pngs(rendered_notebook(count))


@pytest.mark.parametrize("encoded", ["not base64!", base64.b64encode(b"not a PNG").decode(), 1])
def test_malformed_png_output_is_rejected(encoded):
    notebook = rendered_notebook()
    notebook.cells[0].outputs[1].data["image/png"] = encoded
    with pytest.raises(ValueError, match="PNG"):
        export.extract_pngs(notebook)


def test_export_writes_ordered_pngs_and_hashes_without_source_or_text_changes(
    checkout, tmp_path, fake_execution
):
    before = source_bytes(checkout)
    output = tmp_path / "figures"
    provenance = export.export_figures(output, checkout)
    assert source_bytes(checkout) == before
    assert {path.name for path in output.iterdir()} == {*export.FIGURE_NAMES, "figures.json"}
    assert [entry["path"] for entry in provenance["figures"]] == list(export.FIGURE_NAMES)
    for index, entry in enumerate(provenance["figures"]):
        exported = (output / entry["path"]).read_bytes()
        assert exported == png(index)
        assert entry["sha256"] == hashlib.sha256(exported).hexdigest()
    for name, filename in sd.CSV_FILES.items():
        assert provenance["source_csvs"][name]["path"] == f"data/{filename}"
        assert (
            provenance["source_csvs"][name]["sha256"]
            == hashlib.sha256(before[Path("data") / filename]).hexdigest()
        )
    assert (
        provenance["notebook"]["sha256"]
        == hashlib.sha256(before[Path("notebooks/explore_data.ipynb")]).hexdigest()
    )
    assert (
        provenance["implementation"]["sha256"]
        == hashlib.sha256(Path(export.__file__).read_bytes()).hexdigest()
    )
    metadata = (output / "figures.json").read_text()
    assert json.loads(metadata) == provenance
    assert "synthetic private text" not in metadata
    assert str(checkout) not in metadata
    assert provenance["inputs_unchanged"] is True
    assert "unverified" in " ".join(provenance["limits"])


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
@pytest.mark.parametrize("source", ["csv", "notebook", "analysis", "manifest"])
def test_output_aliases_cannot_overwrite_source_inputs(checkout, tmp_path, kind, source):
    sources = {
        "csv": checkout / "data" / "sed.csv",
        "notebook": checkout / "notebooks" / "explore_data.ipynb",
        "analysis": checkout / "sensor_data.py",
        "manifest": checkout / "data" / "RECORDING_PROVENANCE.json",
    }
    output = tmp_path / "figures"
    output.mkdir()
    alias = output / ("figures.json" if source == "manifest" else export.FIGURE_NAMES[0])
    if kind == "symlink":
        alias.symlink_to(sources[source])
    else:
        alias.hardlink_to(sources[source])
    before = source_bytes(checkout)
    with pytest.raises(ValueError, match="overwrite"):
        export.export_figures(output, checkout)
    assert source_bytes(checkout) == before
    assert len(list(output.iterdir())) == 1


def test_every_destination_is_checked_before_execution_or_writing(checkout, tmp_path, monkeypatch):
    output = tmp_path / "figures"
    output.mkdir()
    first = output / export.FIGURE_NAMES[0]
    first.write_bytes(b"preserved")
    (output / export.FIGURE_NAMES[-1]).mkdir()
    monkeypatch.setattr(export, "_execute_notebook", lambda *args: pytest.fail("must not execute"))
    with pytest.raises(ValueError, match="regular file"):
        export.export_figures(output, checkout)
    assert first.read_bytes() == b"preserved"
    assert not (output / "figures.json").exists()


def test_two_outputs_cannot_share_a_file(checkout, tmp_path):
    output = tmp_path / "figures"
    output.mkdir()
    first = output / export.FIGURE_NAMES[0]
    first.write_bytes(b"preserved")
    (output / "figures.json").hardlink_to(first)
    with pytest.raises(ValueError, match="separate files"):
        export.export_figures(output, checkout)
    assert first.read_bytes() == b"preserved"


def test_source_change_during_execution_rejects_export(checkout, tmp_path, monkeypatch):
    def change_input(source, root):
        (root / "data" / "sed.csv").write_text("value\n2\n", encoding="utf-8")
        return rendered_notebook()

    monkeypatch.setattr(export, "_execute_notebook", change_input)
    output = tmp_path / "figures"
    with pytest.raises(ValueError, match="changed during notebook execution"):
        export.export_figures(output, checkout)
    assert not output.exists()


def test_incomplete_render_does_not_write_any_figures(checkout, tmp_path, monkeypatch):
    monkeypatch.setattr(export, "_execute_notebook", lambda *args: rendered_notebook(5))
    output = tmp_path / "figures"
    before = source_bytes(checkout)
    with pytest.raises(ValueError, match="Expected six"):
        export.export_figures(output, checkout)
    assert not output.exists()
    assert source_bytes(checkout) == before


def test_optional_notebook_dependencies_have_an_install_message(checkout, monkeypatch):
    original_import = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == "nbclient":
            raise ImportError("synthetic missing optional dependency")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    with pytest.raises(ValueError, match="pip install"):
        export._execute_notebook(b"{}", checkout)


def test_cli_requires_destination_and_explains_missing_source_checkout(tmp_path, capsys):
    with pytest.raises(SystemExit) as result:
        export.main([])
    assert result.value.code == 2
    output = tmp_path / "figures"
    assert export.main(["--root", str(tmp_path), "--output-dir", str(output)]) == 1
    assert "source checkout" in capsys.readouterr().err
    assert not output.exists()


def test_small_real_notebook_exports_figures_in_memory(checkout, tmp_path):
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell(
                "from IPython.display import display\n"
                "import matplotlib.pyplot as plt\n"
                "print('synthetic private text')\n"
                "for index in range(6):\n"
                "    fig, ax = plt.subplots(figsize=(1, 1))\n"
                "    ax.plot([0, 1], [index, index + 1])\n"
                "    display(fig)\n"
                "    plt.close(fig)\n",
                outputs=rendered_notebook(1).cells[0].outputs,
            )
        ]
    )
    path = checkout / "notebooks" / "explore_data.ipynb"
    nbformat.write(notebook, path)
    before = source_bytes(checkout)
    output = tmp_path / "figures"
    provenance = export.export_figures(output, checkout)
    assert source_bytes(checkout) == before
    assert len(provenance["figures"]) == 6
    for name in export.FIGURE_NAMES:
        image = (output / name).read_bytes()
        assert image.startswith(export.PNG_SIGNATURE) and len(image) > 100
    assert "synthetic private text" not in (output / "figures.json").read_text()
