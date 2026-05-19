variable "azure_account_url" {
  type        = string
  description = "URL where Azure container is held"
}

variable "azure_client_id" {
  type        = string
}

variable "azure_tenant_id" {
  type        = string
}

variable "dest_account_id" {
  type        = string
  description = "Account ID of the destination bucket"
}

variable "dest_bucket_alias" {
  type        = string
  description = "Alias of destination bucket"
}
