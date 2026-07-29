# app/media/metrics.py

from prometheus_client import Counter, Histogram, Gauge

media_processed_total = Counter(
    'media_processed_total',
    'Total number of media processing attempts',
    ['status']  # succeeded, failed, retried
)

media_processing_duration = Histogram(
    'media_processing_duration_seconds',
    'Time spent processing media',
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]
)

media_queue_size = Gauge(
    'media_queue_size',
    'Number of media items in queue'
)
