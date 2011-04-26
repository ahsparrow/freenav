from collections import deque

class FreeLog(deque):
    """Class to store a log of recent x/y fixes"""
    def __init__(self, max_duration=600):
        deque.__init__(self)
        self.max_duration = max_duration
        self.log_flag = False

    def start(self):
        """Start logging, create a new deque"""
        self.clear()
        self.log_flag = True

    def stop(self):
        """Stop logging"""
        self.log_flag = False

    def update(self, x, y, utc):
        """Log a single fix"""
        if self.log_flag:
            self.append((utc, (x, y)))

            # Truncate to maximum length
            if (self[-1][0] - self[0][0]) > self.max_duration:
                self.popleft()
