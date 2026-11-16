variable "environment" {
  type = string
}

variable "crawl_visibility_timeout_seconds" {
  description = "Initial visibility of a received message. app/worker.py heartbeats extend it (JOB_VISIBILITY_TIMEOUT_SECONDS) for as long as the job runs, so this only bounds how long a job held by a dead worker waits before another worker retries it."
  type        = number
  default     = 900
}

variable "ingest_visibility_timeout_seconds" {
  description = "Same as crawl_visibility_timeout_seconds: heartbeats from app/worker.py keep long ingest runs invisible, so this doesn't need to exceed the longest run."
  type        = number
  default     = 900
}

variable "max_receive_count" {
  description = "Receives allowed before a message moves to its DLQ. Keep JOB_MAX_ATTEMPTS in the api/worker ConfigMaps equal to this."
  type        = number
  default     = 3
}

variable "tags" {
  type    = map(string)
  default = {}
}
