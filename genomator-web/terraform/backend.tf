terraform {
  backend "s3" {
    # update following as needed
    bucket         = "terraform-states-genomator-website"
    key            = "example"
    region         = "ap-southeast-2"
  }
}
