# SubControl

## Technology Stack
> Python Application
> REST API
> SQLite Database
> Authentication using OpenID Connect using Keycloak

### General
Secrets are maintained in an .env file in the development and not to be integrated into git.

### Development Environment
> Local Execution
> Frontend and Backend must be validatable
> Authentication is disabled and a dummy user assumed to allow local execution for testing purposes

### Production Environment
> Dockerfile to be created
> docker-compose file to be created
  It should contain ports and volumes

## Application Design

### General
The application is intended to manage recurring subscriptions and especially their payments. They should be maintained manually or being uploadable.

### AI Integration
A chat interface is to be implemented.

OpenAI compatible API should be integrated for analysis against the subscriptions and new subscriptions should be addable.

### MCP Server
All main activities in the application are available in an mcp server to ensure a proper integration into claude is possible.

### Datamodel

*Bucket*
A bucket is the element that is used for authorizations. Users are always assigned to buckets. A bucket has a name and an automatically generated internal ID.

*Subscription*
A subscription is assigned to a buchet and contains the following fields:
* ID: Automatically generated and used internally for referencing
* Name: Title of the subscription
* Provider: Provider of the subscriptions existing records are offered as a dropdown, new ones can be created on the run
* Recurring Interval:
  Values: Daily, Weekly, Monthly, Quarterly, Half-Year, Yearly
* Recurring Date: Selection when the last payment took place.
* Image to be determined automatically using an apropriate web serach.
  It should be generated uwing the Name and Provider.
* Category: Different Categories like (e.g. Haushalt, Streaming)
  They are offered as drop-down and new ones can be created

*User*
* Username
* Last Login
* Assigned Buckets
* Is Admin: Only admins are allowed to assign users to buckets (First User logging in should always be admin)

### Process
The process in the application is as follows:
User logs in -> (First User is Admin) -> A Bucket needs to be create -> Subscriptions in the Bucket to be created -> Dashboard is offered showing overall costs per month and next upcoming payments

### Views

All lists offer sorting by available columns and an application wide search is available to search for users, buckets and subscriptions.

*Dashboard*
* Overall spendings are shown.
* They are broken down to monthly spendings selectable either by average or real.
* Filtering by bucket, subscription and category is available

*Buckets*
* A list is shown offering CRUD Operations
* The detail Page allows modifying Buckets details
* ID can't be changed and is not shown
* A Bucket can be selected to maintain the subscriptions maintained.
* Edit is separate of the subscription maintenance view.

*Subscriptions*
After selecting a bucket the subscriptions in the bucket can be maintained.
It is showing a list with CRUD Operations.

## Development Guidelines

### General
> You always write clean and commented code
> Parts that can be separated are always separeted as modules
> General functions are to be resused from libraries
> An extensive documentation of the implementation is to be created in md files to ease navigation for coding agents.

### Frontend
> Always create modern intuitive designs in a light layout.
> All components are expected to be responsive
> Use icons where they make sense

### Database
> A relational database scheme is to be created
> Updates to the database must be versioned to ensure proper updates without data loss
> Each startup of the application the current version of the database should be checked and updates being applied if available.

### Development Process
> All implementations must be revised
> A set of automtic tests are to be created
>> All API Endpoints must be tested with respective extensive calls
>> Frontend must be tested using a testing framework
>> All standard processes are to be tested and verified
> If needed code is to be refectored
> Test driven developments to be applied: First create use cases that explain what's expected as test, then implement then execute the tests and check if they succeed.
> All code is to be committed and pushed to git
> The application has a version
> After each major development step the spefication and readme is to be updated