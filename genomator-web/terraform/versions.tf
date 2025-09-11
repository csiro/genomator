terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }

    null = {
      source  = "hashicorp/null"
      version = "3.2.2"
    }

    external = {
      source  = "hashicorp/external"
      version = "2.3.3"
    }

    docker = {
      source  = "kreuzwerker/docker"
      version = ">= 3.0"
    }
  }
}
