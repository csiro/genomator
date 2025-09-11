# allow cloudfront to access s3
resource "aws_s3_bucket_policy" "app_website_access" {
  bucket = aws_s3_bucket.app_bucket.id
  policy = data.aws_iam_policy_document.app_website_access.json
}

# iam policy
data "aws_iam_policy_document" "app_website_access" {
  statement {
    principals {
      type = "Service"
      identifiers = [
        "cloudfront.amazonaws.com"
      ]
    }

    actions = [
      "s3:GetObject"
    ]

    resources = [
      "${aws_s3_bucket.app_bucket.arn}/frontend/*",
    ]

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values = [
        aws_cloudfront_distribution.app_distribution.arn
      ]
    }
  }
}


