"""Le paquet app.models doit enregistrer tous les modèles à lui seul.

Les scripts d'exploitation (app/scripts/) ne chargent pas app.main : si un
modèle manque dans app/models/__init__.py, SQLAlchemy échoue à résoudre les
relations déclarées par nom (ex. ``relationship("Role")``).
"""

import subprocess
import sys


def test_app_models_suffit_a_configurer_les_mappers():
    code = (
        "import app.models.conversation\n"
        "from sqlalchemy.orm import configure_mappers\n"
        "configure_mappers()\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
