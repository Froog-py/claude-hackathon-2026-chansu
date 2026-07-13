"""Import-smoke for the connect-a-model UI. Rendering is verified in the browser preview; this only
guards that the module imports with no Streamlit run context and exposes render_model_setup."""


def test_render_model_setup_importable():
    from chansu.ui import models as ui_models

    assert hasattr(ui_models, "render_model_setup")
