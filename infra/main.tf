# Azure for Students subscription. Everything here fits in a few dollars a month.
terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.0" }
  }
}

provider "azurerm" {
  features {}
  # Only the providers we use (Storage, Web, Consumption); registering all of them fails on student subscriptions.
  resource_provider_registrations = "none"
  resource_providers_to_register  = ["Microsoft.Storage", "Microsoft.Web", "Microsoft.Consumption"]
  subscription_id                 = var.subscription_id
}

variable "subscription_id" { type = string }
variable "alert_email" { type = string }
variable "location" { default = "germanywestcentral" } # student subscriptions only allow a few regions
variable "name" { default = "belakehouse" }

data "azurerm_subscription" "current" {}

resource "azurerm_resource_group" "rg" {
  name     = "rg-${var.name}"
  location = var.location
}

# The lake: hierarchical namespace = ADLS Gen2.
resource "azurerm_storage_account" "lake" {
  name                     = "${var.name}lake"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  is_hns_enabled           = true
  min_tls_version          = "TLS1_2"
}

resource "azurerm_storage_container" "layer" {
  for_each           = toset(["bronze", "silver", "gold"])
  name               = each.key
  storage_account_id = azurerm_storage_account.lake.id
}

# Function app on Flex Consumption: pay per run, free grant covers a 15-min timer.
resource "azurerm_storage_account" "func" {
  name                     = "${var.name}func"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  min_tls_version          = "TLS1_2"
}

resource "azurerm_storage_container" "deploy" {
  name               = "deploy"
  storage_account_id = azurerm_storage_account.func.id
}

resource "azurerm_service_plan" "plan" {
  name                = "plan-${var.name}"
  resource_group_name = azurerm_resource_group.rg.name
  location            = var.location
  os_type             = "Linux"
  sku_name            = "FC1"
}

resource "azurerm_function_app_flex_consumption" "ingest" {
  name                       = "func-${var.name}"
  resource_group_name        = azurerm_resource_group.rg.name
  location                   = var.location
  service_plan_id            = azurerm_service_plan.plan.id
  storage_container_type     = "blobContainer"
  storage_container_endpoint = "${azurerm_storage_account.func.primary_blob_endpoint}${azurerm_storage_container.deploy.name}"
  # identity auth here leaves AzureWebJobsStorage with an empty key (provider bug), so use the key
  storage_authentication_type = "StorageAccountConnectionString"
  storage_access_key          = azurerm_storage_account.func.primary_access_key
  runtime_name                = "python"
  runtime_version             = "3.12"
  maximum_instance_count      = 40
  instance_memory_in_mb       = 512

  identity { type = "SystemAssigned" }
  site_config {}

  app_settings = {
    LAKE_ACCOUNT = azurerm_storage_account.lake.name
  }
}

resource "azurerm_role_assignment" "func_writes_lake" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_function_app_flex_consumption.ingest.identity[0].principal_id
}

resource "azurerm_role_assignment" "func_reads_deploy" {
  scope                = azurerm_storage_account.func.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azurerm_function_app_flex_consumption.ingest.identity[0].principal_id
}

# Email me long before the student credit is gone.
resource "azurerm_consumption_budget_subscription" "budget" {
  name            = "budget-${var.name}"
  subscription_id = data.azurerm_subscription.current.id
  amount          = 10
  time_grain      = "Monthly"

  time_period {
    start_date = "2026-10-01T00:00:00Z"
  }

  notification {
    operator       = "GreaterThan"
    threshold      = 50
    contact_emails = [var.alert_email]
  }

  notification {
    operator       = "GreaterThan"
    threshold      = 100
    contact_emails = [var.alert_email]
  }
}

output "function_app" { value = azurerm_function_app_flex_consumption.ingest.name }
output "lake_account" { value = azurerm_storage_account.lake.name }
