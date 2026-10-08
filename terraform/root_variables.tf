variable "azure_account_url" {
  type        = string
  description = "URL where Azure container is held"
  sensitive   = true
}

variable "azure_client_id" {
  type      = string
  sensitive = true
}

variable "azure_tenant_id" {
  type      = string
  sensitive = true
}

variable "dest_account_id" {
  type = object({
    dev     = string
    staging = string
    live    = string
  })
  description = "Account IDs of the destination buckets"
  sensitive   = true
}

variable "dest_bucket" {
  type = object({
    dev     = string
    staging = string
    live    = string
  })
  description = "Name of destination buckets"
  sensitive   = true
}


variable "dest_bucket_alias" {
  type = object({
    dev     = string
    staging = string
    live    = string
  })
  description = "Aliases of destination buckets"
  sensitive   = true
}

variable "container_tool" {
  type    = string
  default = "docker"
}