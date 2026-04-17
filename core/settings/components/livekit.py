import os


LIVEKIT_CONFIG = {
    'URL': 'ws://localhost:7880',
    'API_KEY': 'devkey',
    'API_SECRET': 'MySuperSecretKeyForDev2026AtLeast32CharsLong!!!',   # same sa yaml
}

LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY', 'devkey')
LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET', 'MySuperSecretKeyForDev2026AtLeast32CharsLong!!!')


LIVEKIT_URL = os.getenv('LIVEKIT_URL', 'http://livekit:7880')
LIVEKIT_WS_URL = os.getenv('LIVEKIT_WS_URL', 'ws://127.0.0.1:7880')


# LIVEKIT_URL = 'http://livekit:7880'      # HTTP admin API
# LIVEKIT_WS_URL = 'ws://livekit:7880'     # WebSocket for clients (optional)