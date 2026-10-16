app_name = "agora_integration"
app_title = "Agora Integration"
app_publisher = "CoreAxis Solutions"
app_description = "Reusable user-to-user audio and video calling powered by Agora"
app_email = "lubshad4u4@gmail.com"
app_license = "mit"

required_apps = ["flutter_utils"]
after_install = "agora_integration.install.after_install"
scheduler_events = {"cron": {"* * * * *": ["agora_integration.tasks.expire_calls"]}}
device_credential_revoked = ["agora_integration.services.voip_devices.deactivate_device_voip"]
doc_events = {
	"Flutter Device Credential": {
		"on_update": "agora_integration.services.voip_devices.credential_updated",
		"on_trash": "agora_integration.services.voip_devices.credential_deleted",
	}
}

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "agora_integration",
# 		"logo": "/assets/agora_integration/logo.png",
# 		"title": "Agora Integration",
# 		"route": "/agora_integration",
# 		"has_permission": "agora_integration.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/agora_integration/css/agora_integration.css"
# app_include_js = "/assets/agora_integration/js/agora_integration.js"

# include js, css files in header of web template
# web_include_css = "/assets/agora_integration/css/agora_integration.css"
# web_include_js = "/assets/agora_integration/js/agora_integration.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "agora_integration/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "agora_integration/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "agora_integration.utils.jinja_methods",
# 	"filters": "agora_integration.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "agora_integration.install.before_install"
# after_install = "agora_integration.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "agora_integration.uninstall.before_uninstall"
# after_uninstall = "agora_integration.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "agora_integration.utils.before_app_install"
# after_app_install = "agora_integration.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "agora_integration.utils.before_app_uninstall"
# after_app_uninstall = "agora_integration.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "agora_integration.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "agora_integration.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["agora_integration.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"agora_integration.tasks.all"
# 	],
# 	"daily": [
# 		"agora_integration.tasks.daily"
# 	],
# 	"hourly": [
# 		"agora_integration.tasks.hourly"
# 	],
# 	"weekly": [
# 		"agora_integration.tasks.weekly"
# 	],
# 	"monthly": [
# 		"agora_integration.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "agora_integration.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "agora_integration.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "agora_integration.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "agora_integration.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["agora_integration.utils.before_request"]
# after_request = ["agora_integration.utils.after_request"]

# Job Events
# ----------
# before_job = ["agora_integration.utils.before_job"]
# after_job = ["agora_integration.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"agora_integration.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
