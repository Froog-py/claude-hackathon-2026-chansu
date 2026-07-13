"""Import-smoke for the Add-compound UI. Streamlit rendering is verified in the browser preview;
this only guards that the module imports with no Streamlit run context and exposes render_ingest."""


def test_render_ingest_is_importable():
    from chansu.ui import ingest as ui_ingest

    assert hasattr(ui_ingest, "render_ingest")
