resource "aws_s3_bucket" "app_bucket" {
  bucket_prefix = "${var.app-name}-bucket-"

  tags = var.tags
}

