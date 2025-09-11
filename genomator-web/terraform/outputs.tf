output "distribution_url" {
  value       = "https://${aws_cloudfront_distribution.app_distribution.domain_name}"
  description = "FRONTEND URL"
}
