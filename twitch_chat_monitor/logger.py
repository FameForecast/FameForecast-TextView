import csv
import os
from datetime import datetime, timezone

class DataLogger:
    def __init__(self, data_dir):
        # Store the passed directory
        self.data_dir = data_dir
        # Extract Experiment ID from the folder name (e.g., "20260101_160422")
        self.experiment_id = data_dir.name
        
        # Define paths based on the passed directory
        self.chat_log = data_dir / "chat_messages.csv"
        self.transcript_log = data_dir / "transcripts.csv"
        self.system_log = data_dir / "system_events.csv"
        self.insight_log = data_dir / "rnd_insights.csv"

        # Open files (Append mode)
        self.chat_file = open(self.chat_log, 'a', newline='', encoding='utf-8')
        self.chat_writer = csv.writer(self.chat_file)

        self.transcript_file = open(self.transcript_log, 'a', newline='', encoding='utf-8')
        self.transcript_writer = csv.writer(self.transcript_file)

        self.system_file = open(self.system_log, 'a', newline='', encoding='utf-8')
        self.system_writer = csv.writer(self.system_file)

        self.insight_writer = None
        self.insight_file = None

        self._init_csv_headers()

    def _init_csv_headers(self):
        # Only write headers if the file is empty (size 0)
        if os.stat(self.chat_log).st_size == 0:
            self.chat_writer.writerow(['timestamp', 'channel', 'user', 'message_type',
                                     'message', 'experiment_id', 'irc_delay_ms', 'msg_length'])
        
        if os.stat(self.transcript_log).st_size == 0:
            self.transcript_writer.writerow(['timestamp', 'channel', 'transcript_text',
                                            'audio_chunk_start', 'audio_chunk_end', 'confidence'])
        
        if os.stat(self.system_log).st_size == 0:
            self.system_writer.writerow(['timestamp', 'event_type', 'channel',
                                       'details', 'severity'])

    def log_chat(self, timestamp, channel, user, msg_type, message, irc_delay=0):
        # Use self.experiment_id (from folder name) instead of global import
        self.chat_writer.writerow([timestamp, channel, user.lower(), msg_type, message,
                                   self.experiment_id, irc_delay, len(message)])
        self.chat_file.flush()

    def log_transcript(self, timestamp, channel, text, chunk_start, chunk_end, confidence=1.0):
        self.transcript_writer.writerow([timestamp, channel, text, chunk_start,
                                         chunk_end, confidence])
        self.transcript_file.flush()

    def log_system(self, timestamp, event_type, channel, details, severity="INFO"):
        self.system_writer.writerow([timestamp, event_type, channel, details, severity])
        self.system_file.flush()

    def log_insight(self, timestamp, channel, user, insight_type, details, confidence, experiment_id):
        if self.insight_writer is None:
            if not self.insight_log.exists():
                self.insight_file = open(self.insight_log, 'w', newline='', encoding='utf-8')
                self.insight_writer = csv.writer(self.insight_file)
                self.insight_writer.writerow(['timestamp', 'channel', 'user', 'insight_type',
                                             'details', 'confidence', 'experiment_id'])
            else:
                self.insight_file = open(self.insight_log, 'a', newline='', encoding='utf-8')
                self.insight_writer = csv.writer(self.insight_file)

        self.insight_writer.writerow([timestamp, channel, user.lower(), insight_type, details,
                                      confidence, experiment_id])
        self.insight_file.flush()

    def close_files(self):
        for f in [self.chat_file, self.transcript_file, self.system_file, self.insight_file]:
            if f and not f.closed:
                f.close()