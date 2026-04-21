module "config" {
  source  = "./da-terraform-configurations"
  project = "dr2"
}

terraform {
  backend "s3" {
    bucket       = "dri-terraform-state-store"
    key          = "farm-survey-terraform.state"
    region       = "eu-west-2"
    encrypt      = true
    use_lockfile = true
  }
}
provider "aws" {
  region = "eu-west-2"
}
