import multiprocessing

# Gunicorn configuration for Render
bind = "0.0.0.0:10000"
workers = 2
timeout = 120
accesslog = "-"
errorlog = "-"
capture_output = True
enable_stdio_inheritance = True
