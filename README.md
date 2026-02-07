# FameForecast TextView

Multi-stream chat viewer with live audio transcription for content creators.

## Download

Get the latest release from the [Releases](https://github.com/FameForecast/FameForecast-TextView/releases) page.

## Features

- Monitor multiple Twitch streams simultaneously
- Real-time audio transcription (speech-to-text)
- Web-based interface - runs in your browser
- No additional downloads required - everything bundled
- All processing done locally on your machine

## Quick Start

1. Download `FameForecastTextView.zip` from Releases
2. Extract the zip file
3. Run `FameForecastTextView.exe`
4. Browser opens automatically to http://localhost:8080
5. Complete the setup wizard (first run only)
6. Select channels to monitor

## Requirements

- Windows 10/11
- Internet connection (for Twitch streams)

## Building from Source

```bash
pip install -r requirements.txt
python build_web.py
```

The built executable will be in `dist/FameForecastTextView/`.

## License

MIT License
