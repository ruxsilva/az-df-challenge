"""Azure Functions app entry point (Python v2 model). Registers the blueprints."""

import azure.durable_functions as df
import azure.functions as func

from src.activities.container_ops import bp as activities_bp
from src.orchestrators.container_lifecycle import bp as lifecycle_bp
from src.orchestrators.pipeline import bp as pipeline_bp
from src.starters.http_starter import bp as http_bp

app = df.DFApp(http_auth_level=func.AuthLevel.FUNCTION)

app.register_functions(http_bp)
app.register_functions(pipeline_bp)
app.register_functions(lifecycle_bp)
app.register_functions(activities_bp)
