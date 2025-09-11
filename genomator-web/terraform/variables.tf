# App variables
variable "app-name" {
  type        = string
  default     = "genomator-web-website"
  description = "name of the app you're deploying"
}

# Common variables
variable "region" {
  type        = string
  default     = "ap-southeast-2"
  description = "deployment region"
}

variable "tags" {
  type = map(any)
  default = {
    NAME = "template"
    STAGE = "dev"
  }
  description = "Default tags for the deployment"
}

# Angulart build commands
variable "webapp-dir" {
  type        = string
  description = "Relative path to webapp"
  default     = "../frontend/"
}

variable "install-command" {
  type        = string
  description = "Install command to install requirements"
  default     = "pnpm install"
}


variable "build-command" {
  type        = string
  description = "Build command to build the webapp"
  default     = "./node_modules/.bin/ng build --configuration production --subresource-integrity"
}

variable "build-destination" {
  type        = string
  description = "Path to built source"
  default     = "../frontend/dist/genomator-web/"
}
