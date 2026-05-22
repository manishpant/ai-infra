variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "project_name" {
  description = "Project name for tagging"
  type        = string
  default     = "terraform-project"
}

variable "bucket_name" {
  description = "S3 bucket name (must be globally unique)"
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]*[a-z0-9]$", var.bucket_name))
    error_message = "Bucket name must start and end with lowercase letter or number, contain only lowercase letters, numbers, and hyphens."
  }
}

variable "enable_versioning" {
  description = "Enable S3 bucket versioning"
  type        = bool
  default     = true
}

variable "enable_mfa_delete" {
  description = "Enable MFA delete (requires versioning)"
  type        = bool
  default     = false
}

variable "enable_server_side_encryption" {
  description = "Enable server-side encryption with SSE-S3"
  type        = bool
  default     = true
}

variable "enable_public_access_block" {
  description = "Block all public access to bucket"
  type        = bool
  default     = true
}

variable "enable_logging" {
  description = "Enable S3 access logging"
  type        = bool
  default     = false
}

variable "log_bucket_name" {
  description = "S3 bucket name for access logs (only needed if enable_logging is true)"
  type        = string
  default     = ""
}

variable "lifecycle_rules" {
  description = "S3 lifecycle rules for object expiration and transitions"
  type = list(object({
    id                 = string
    enabled            = bool
    prefix             = optional(string, "")
    expiration_days    = optional(number)
    transition_days    = optional(number)
    transition_storage = optional(string)
  }))
  default = []
}

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}