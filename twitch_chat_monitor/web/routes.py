# twitch_chat_monitor/web/routes.py
"""
HTTP route handlers for Flask web interface.
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, current_app
from datetime import datetime
import requests

bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    """Main dashboard page"""
    from ..user_config import user_config

    if not user_config.is_setup_complete():
        return redirect(url_for('main.setup'))

    context = current_app.context

    # If no channels selected yet, go to channel selector
    if context and not context.active_channels:
        return redirect(url_for('main.select_channels'))

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    return render_template('index.html', session_id=session_id)


@bp.route('/setup')
def setup():
    """Setup wizard page"""
    redirect_uri = url_for('main.oauth_callback', _external=True)
    return render_template('setup.html',
                           app_name="FameForecastTextView",
                           redirect_uri=redirect_uri)


@bp.route('/select-channels')
def select_channels():
    """Channel selection page"""
    return render_template('channel_selector.html')


@bp.route('/api/setup/save', methods=['POST'])
def save_setup():
    """Save setup configuration"""
    from ..user_config import user_config

    data = request.json

    user_config.update(
        twitch_client_id=data.get('client_id', '').strip(),
        twitch_client_secret=data.get('client_secret', '').strip(),
        access_token=data.get('access_token', ''),
        refresh_token=data.get('refresh_token', ''),
        bot_username=data.get('username', '').strip(),
        main_username=data.get('username', '').strip(),
        setup_complete=True
    )

    return jsonify({'success': True})


@bp.route('/api/setup/status')
def setup_status():
    """Check if setup is complete"""
    from ..user_config import user_config
    return jsonify({'complete': user_config.is_setup_complete()})


@bp.route('/oauth/callback')
def oauth_callback():
    """Handle OAuth redirect from Twitch"""
    code = request.args.get('code')
    error = request.args.get('error')

    if error:
        return f'''
        <html>
        <head><title>Authorization Failed</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px; background: #1e1e1e; color: white;">
            <h1>Authorization Failed</h1>
            <p>Error: {error}</p>
            <p><a href="/setup" style="color: #9147ff;">Try again</a></p>
        </body>
        </html>
        '''

    if code:
        # Return page that sends code back to opener window
        return f'''
        <html>
        <head><title>Authorization Successful</title></head>
        <body style="font-family: Arial; text-align: center; padding: 50px; background: #1e1e1e; color: white;">
            <h1>Authorization Successful!</h1>
            <p>Returning to setup...</p>
            <script>
                // Send code back to opener window
                if (window.opener) {{
                    window.opener.postMessage({{type: 'oauth_code', code: '{code}'}}, '*');
                    window.close();
                }} else {{
                    // If opened in same window, redirect back with code
                    window.location.href = '/setup?code={code}';
                }}
            </script>
        </body>
        </html>
        '''

    return redirect(url_for('main.setup'))


@bp.route('/api/oauth/exchange', methods=['POST'])
def oauth_exchange():
    """Exchange OAuth code for tokens"""
    data = request.json
    code = data.get('code')
    client_id = data.get('client_id')
    client_secret = data.get('client_secret')
    redirect_uri = data.get('redirect_uri') or url_for('main.oauth_callback', _external=True)

    if not all([code, client_id, client_secret]):
        return jsonify({'error': 'Missing required fields'}), 400

    try:
        response = requests.post(
            'https://id.twitch.tv/oauth2/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
                'grant_type': 'authorization_code',
                'redirect_uri': redirect_uri
            }
        )

        if response.status_code == 200:
            token_data = response.json()
            return jsonify({
                'success': True,
                'access_token': token_data.get('access_token'),
                'refresh_token': token_data.get('refresh_token', '')
            })
        else:
            error = response.json().get('message', 'Token exchange failed')
            return jsonify({'error': error}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/channels/live')
def get_live_channels():
    """Get list of live channels with metadata"""
    import time

    context = current_app.context

    if not context:
        return jsonify({'error': 'Not initialized'}), 500

    # Wait for data to be ready (up to 30 seconds)
    # The background thread populates live_data
    max_wait = 30
    waited = 0
    while waited < max_wait:
        live_data = getattr(context, 'live_data', {})
        if live_data:
            break
        time.sleep(0.5)
        waited += 0.5

    live_data = getattr(context, 'live_data', {})
    follower_counts = getattr(context, 'follower_counts', {})

    channels = []
    for channel, data in live_data.items():
        channels.append({
            'name': channel,
            'game': data.get('game', 'Unknown'),
            'viewers': data.get('viewers', 0),
            'followers': follower_counts.get(channel.lower(), 0)
        })

    # Sort by viewers (low to high)
    channels.sort(key=lambda x: x['viewers'])

    return jsonify({'channels': channels, 'ready': True})


@bp.route('/api/channels/active')
def get_active_channels():
    """Get list of currently active/monitored channels"""
    context = current_app.context

    if not context:
        return jsonify({'channels': []})

    active = list(getattr(context, 'active_channels', set()))
    return jsonify({'channels': active})


@bp.route('/api/channels/join', methods=['POST'])
def join_channel():
    """Join a channel"""
    context = current_app.context
    data = request.json
    channel = (data.get('channel') or '').strip().lower()

    if not channel:
        return jsonify({'error': 'No channel specified'}), 400

    if not context:
        return jsonify({'error': 'Not initialized'}), 500

    # Add to active channels so backend workers start
    context.active_channels.add(channel)
    if hasattr(context, 'selected_channels'):
        context.selected_channels.add(channel)

    # Emit a join signal via queue for any connected clients
    context.gui_queue.put(('GUI_JOIN_NOW', 'SYSTEM', channel))

    return jsonify({'success': True, 'channel': channel})


@bp.route('/api/channels/select', methods=['POST'])
def select_channels_api():
    """Set the initial list of channels to monitor"""
    context = current_app.context
    data = request.json
    channels = [str(ch).strip().lower() for ch in data.get('channels', []) if str(ch).strip()]

    if not context:
        return jsonify({'error': 'Not initialized'}), 500

    # Add channels directly to active_channels (not just selected)
    for ch in channels:
        context.active_channels.add(ch)

    # Also set selected_channels for the worker thread to pick up
    context.selected_channels = set(channels)

    return jsonify({'success': True, 'channels': channels})
