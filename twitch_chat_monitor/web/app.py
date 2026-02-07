# twitch_chat_monitor/web/app.py
"""
Flask application factory with SocketIO integration.
"""
from flask import Flask
from flask_socketio import SocketIO
import os

# Create SocketIO instance at module level for import by other modules
socketio = SocketIO()


def create_app(context=None):
    """
    Create and configure the Flask application.

    Args:
        context: RuntimeContext with queues and state (optional for setup-only mode)

    Returns:
        Configured Flask app
    """
    # Get the web package directory for static/templates
    web_dir = os.path.dirname(os.path.abspath(__file__))

    app = Flask(__name__,
                static_folder=os.path.join(web_dir, 'static'),
                template_folder=os.path.join(web_dir, 'templates'))

    # Secret key for sessions
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24))

    # Store context for route handlers
    app.context = context

    # Import and register routes
    from .routes import bp as routes_bp
    app.register_blueprint(routes_bp)

    # Initialize SocketIO
    # Using 'threading' async_mode for Windows compatibility
    # This works well with multiprocessing queues
    socketio.init_app(app,
                      async_mode='threading',
                      cors_allowed_origins="*",
                      logger=False,
                      engineio_logger=False)

    # Register socket event handlers
    from . import socket_events
    socket_events.register(socketio, context)

    return app
