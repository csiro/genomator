resource "aws_acm_certificate" "cert" {
  domain_name       = "genomator.csiro.au"
  validation_method = "EMAIL"
  tags              = var.tags

  lifecycle {
    create_before_destroy = true
  }

  validation_option {
    domain_name       = "genomator.csiro.au"
    validation_domain = "csiro.au"
  }
}
