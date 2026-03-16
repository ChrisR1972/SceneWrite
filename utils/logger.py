"""
Logging utility for SceneWrite.
Safe to import - never raises exceptions.
"""

# Wrap everything in try/except to ensure module can always be imported
try:
    import logging
    import os
    _LOGGING_AVAILABLE = True
except Exception:
    _LOGGING_AVAILABLE = False
    import os


def get_log_file_path():
    """Get the path to the log file."""
    try:
        # Get the application directory
        if os.name == 'nt':  # Windows
            appdata = os.getenv('APPDATA', '')
            if not appdata:
                # Fallback to current directory if APPDATA not set
                app_dir = os.path.join(os.getcwd(), 'logs')
            else:
                app_dir = os.path.join(appdata, 'SceneWrite')
        else:  # Linux/Mac
            app_dir = os.path.join(os.path.expanduser('~'), '.scenewrite')
        
        # Create directory if it doesn't exist
        try:
            os.makedirs(app_dir, exist_ok=True)
        except (OSError, PermissionError):
            # Fallback to current directory if we can't create the directory
            app_dir = os.path.join(os.getcwd(), 'logs')
            try:
                os.makedirs(app_dir, exist_ok=True)
            except:
                pass
        
        # Log file path
        log_file = os.path.join(app_dir, 'scenewrite.log')
        return log_file
    except Exception:
        # Ultimate fallback - use current directory
        try:
            return os.path.join(os.getcwd(), 'scenewrite.log')
        except:
            return 'scenewrite.log'


def setup_logger():
    """Setup the application logger."""
    if not _LOGGING_AVAILABLE:
        # Return a dummy object that has the same interface
        class DummyLogger:
            def error(self, *args, **kwargs):
                pass
            def info(self, *args, **kwargs):
                pass
            def debug(self, *args, **kwargs):
                pass
            def warning(self, *args, **kwargs):
                pass
        return DummyLogger()
    
    try:
        log_file = get_log_file_path()
        
        # Create logger
        logger = logging.getLogger('SceneWrite')
        logger.setLevel(logging.DEBUG)
        
        # Remove existing handlers to avoid duplicates
        logger.handlers = []
        
        # Create file handler with error handling
        try:
            file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            
            # Create formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(formatter)
            
            # Add handler to logger
            logger.addHandler(file_handler)
        except (OSError, PermissionError, IOError, Exception) as e:
            # If we can't create the file handler, create a null handler
            # This prevents errors but doesn't log
            try:
                logger.addHandler(logging.NullHandler())
            except:
                pass
        
        return logger
    except Exception:
        # If everything fails, return a logger with null handler
        try:
            logger = logging.getLogger('SceneWrite')
            logger.addHandler(logging.NullHandler())
            return logger
        except:
            # Ultimate fallback - return dummy logger
            class DummyLogger:
                def error(self, *args, **kwargs):
                    pass
                def info(self, *args, **kwargs):
                    pass
                def debug(self, *args, **kwargs):
                    pass
                def warning(self, *args, **kwargs):
                    pass
            return DummyLogger()


# Global logger instance
_logger = None


def get_logger():
    """Get the global logger instance."""
    global _logger
    try:
        if _logger is None:
            _logger = setup_logger()
        return _logger
    except Exception:
        # Return a null logger if setup fails
        logger = logging.getLogger('SceneWrite')
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())
        return logger


def log_error(message, exc_info=None):
    """Log an error message."""
    try:
        logger = get_logger()
        logger.error(message, exc_info=exc_info)
    except Exception:
        print(f"ERROR: {message}")


def log_exception(message, exception):
    """Log an exception with full traceback."""
    try:
        logger = get_logger()
        import traceback
        logger.error(f"{message}: {str(exception)}\n{traceback.format_exc()}", exc_info=exception)
    except Exception:
        # If logging fails, at least print to console
        import traceback
        print(f"ERROR: {message}: {exception}")
        traceback.print_exc()


def log_info(message):
    """Log an info message."""
    try:
        logger = get_logger()
        logger.info(message)
    except Exception:
        pass  # Silently fail for info messages


def log_debug(message):
    """Log a debug message."""
    try:
        logger = get_logger()
        logger.debug(message)
    except Exception:
        pass  # Silently fail for debug messages


def log_warning(message):
    """Log a warning message."""
    try:
        logger = get_logger()
        logger.warning(message)
    except Exception:
        print(f"WARNING: {message}")
