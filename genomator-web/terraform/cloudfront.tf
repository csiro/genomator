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
    allowed_methods            = ["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"]
    cached_methods             = ["GET", "HEAD"]
    viewer_protocol_policy     = "redirect-to-https"
    target_origin_id           = local.s3_web_origin_id
    cache_policy_id            = data.aws_cloudfront_cache_policy.app_distribution.id
    compress                   = true
    response_headers_policy_id = aws_cloudfront_response_headers_policy.headers_policy.id
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

resource "aws_cloudfront_response_headers_policy" "headers_policy" {
  name = "genomator-security-headers-policy"

  security_headers_config {
    strict_transport_security {
      override                   = true
      access_control_max_age_sec = 63072000
      include_subdomains         = true
      preload                    = true
    }

    content_type_options {
      override = true
    }

    frame_options {
      override     = true
      frame_option = "DENY"
    }

    content_security_policy {
      content_security_policy = "frame-ancestors 'self';block-all-mixed-content;default-src 'none';script-src 'self' 'report-sample' 'wasm-unsafe-eval' cdnjs.cloudflare.com cdn.jsdelivr.net;style-src 'self' 'report-sample' cdnjs.cloudflare.com cdn.jsdelivr.net https://fonts.googleapis.com/ https://fonts.gstatic.com/ 'unsafe-inline';object-src 'none';frame-src 'self';child-src 'self';img-src 'self' data: cdnjs.cloudflare.com cdn.jsdelivr.net https://fonts.gstatic.com/;font-src 'self' cdnjs.cloudflare.com cdn.jsdelivr.net https://fonts.googleapis.com/ https://fonts.gstatic.com/;connect-src 'self' cdnjs.cloudflare.com cdn.jsdelivr.net https://fonts.googleapis.com/ https://fonts.gstatic.com/;manifest-src 'self';base-uri 'self';form-action 'self';media-src 'self';worker-src 'self';"
      override                = true
    }

    referrer_policy {
      override        = true
      referrer_policy = "no-referrer"
    }
  }
}
