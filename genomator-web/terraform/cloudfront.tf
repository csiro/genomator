locals {
  s3_web_origin_id      = "${var.app-name}-web-origin"
  s3_job_data_origin_id = "${var.app-name}-job-data-origin"
}

resource "aws_cloudfront_origin_access_control" "app_access_control" {
  name                              = "${var.app-name}_access_control"
  description                       = "${var.app-name} access control Policy"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "app_distribution" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_distribution" "app_distribution" {
  origin {
    domain_name              = aws_s3_bucket.app_bucket.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.app_access_control.id
    origin_id                = local.s3_web_origin_id
    origin_path              = "/frontend"
  }

  tags                = var.tags
  comment             = "${var.app-name} distribution"
  enabled             = true
  is_ipv6_enabled     = true
  http_version        = "http2and3"
  default_root_object = "index.html"

  custom_error_response {
    response_code      = 200
    error_code         = 404
    response_page_path = "/index.html"
  }

  custom_error_response {
    response_code      = 200
    error_code         = 400
    response_page_path = "/index.html"
  }

  custom_error_response {
    response_code      = 200
    error_code         = 403
    response_page_path = "/index.html"
  }

  default_cache_behavior {
    allowed_methods        = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods         = ["GET", "HEAD"]
    viewer_protocol_policy = "redirect-to-https"
    target_origin_id       = local.s3_web_origin_id
    cache_policy_id        = data.aws_cloudfront_cache_policy.app_distribution.id
    compress               = true
  }

  price_class = "PriceClass_200"

  restrictions {
    geo_restriction {
      restriction_type = "none"
      locations        = []
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}
