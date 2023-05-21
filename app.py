import copy
from datetime import datetime
import logging
import jinja2
import json
import os
import re
import traceback
import uuid

from slack_bolt import App
from slack_bolt.oauth import OAuthFlow
from slack_bolt.oauth.oauth_settings import OAuthSettings
from slack_bolt.adapter.socket_mode import SocketModeHandler

import database
import views
import utilities

from pprint import pprint

logging.basicConfig(level=logging.INFO)

app = App(
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
    oauth_settings=OAuthSettings(
        client_id=os.environ["SLACK_CLIENT_ID"],
        client_secret=os.environ["SLACK_CLIENT_SECRET"],
        scopes=os.environ["SLACK_SCOPES"].split(","),
    ),
    oauth_flow=OAuthFlow.sqlite3(
        database=os.environ["OAUTH_DATABASE_STR"],
        token_rotation_expiration_minutes=60 * 24,  # for testing
    ),
)

# Preload templates
homepage_template = None  # json.load(open("templates/home.json", "r"))
delete_enviroment_template = json.load(open("templates/deleteEnvironment.json", "r"))
book_enviroment_template = None #json.load(open("templates/bookEnvironment.json", "r"))
modify_enviroment_template = json.load(open("templates/modifyEnvironment.json", "r"))
error_template = json.load(open("templates/errorPage.json", "r"))

jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader("templates"), autoescape=jinja2.select_autoescape()
)
jinja_env.tests['userHasbooking'] = utilities.userHasBooking
jinja_env.tests['numberBookingsRemaining'] = utilities.numberBookingsRemaining

home_template = jinja_env.get_template("home.json")
add_env_template = jinja_env.get_template("addEnvironment.json")
manage_settings_template = jinja_env.get_template("manageSettings.json")
book_env_template = jinja_env.get_template("bookEnvironment.json")
add_resource_type_template = jinja_env.get_template("addResourceType.json")
modify_resource_type_template = jinja_env.get_template("modifyResourceType.json")
delete_resource_type_template = jinja_env.get_template("deleteResourceType.json")

def refresh_home_template(organisationId, userId, client, resourceTypeId: int = None):
    resourceTypesData = list(database.getResourceTypes(organisationId))

    # If no resources have been defined yet
    if len(resourceTypesData) == 0:
        result = home_template.render(
            data={
                "resourceTypesData": []
            }
        )
        client.views_publish(user_id=userId, view=result)
    
    else:

        if resourceTypeId is None:
            resourceTypeId = resourceTypesData[0][0]

        resourceTypeData = next(
            (
                resourceType
                for resourceType in resourceTypesData
                if resourceType[0] == int(resourceTypeId)
            ),
            None,
        )

        environments = list(database.getEnvironments(organisationId, resourceTypeId))

        # If no environments have been defined yet
        if len(environments) == 0:
            result = home_template.render(
                data={
                    "resourceTypesData": resourceTypesData,
                    "resourceTypeId": resourceTypeId,
                    "resourceTypeName": resourceTypeData[1],
                    "resourceTypeDescription": resourceTypeData[2],
                    "userId": userId
                },
                isAdmin = userId in resourceTypeData[3]
            )
            client.views_publish(user_id=userId, view=result)
        
        else:
            for index, environment in enumerate(environments):
                # Get the bookings for each environment, and append them to the object
                bookings = database.getBookings(organisationId, environment[0], resourceTypeId)
                bookings = utilities.databaseResultToDict(bookings, 1)
                validBookingKeys = utilities.getValidBookings(environment[3], environment[4])
                environments[index] = tuple(environment) + (bookings, validBookingKeys)
            
            result = home_template.render(
                data={
                    "resourceTypesData": resourceTypesData,
                    "resourceTypeId": resourceTypeId,
                    "resourceTypeName": resourceTypeData[1],
                    "resourceTypeDescription": resourceTypeData[2],
                    "environments": environments,
                    "bookings": utilities.getNextNDays(2),
                    "validDates": None,
                },
                isAdmin = userId in resourceTypeData[3]
            )

            client.views_publish(user_id=userId, view=result)


def refresh_home(organisationId, userId, client, resourceTypeId: int = None):
    generated_template = copy.deepcopy(homepage_template)

    resourceTypesData = database.getResourceTypes(organisationId)
    # If resourceTypes haven't been defined yet only show the settings button
    if len(list(resourceTypesData)) == 0:
        generated_template["blocks"] = generated_template["blocks"][5:]
    else:
        resourceTypesView = views.generate_environment_options(resourceTypesData)
        generated_template["blocks"][0]["elements"][0]["options"] = resourceTypesView
        if resourceTypeId is None:
            generated_template["blocks"][0]["elements"][0][
                "initial_option"
            ] = resourceTypesView[0]
            resourceTypeId = int(list(resourceTypesData)[0][0])

        resourceTypeId = int(resourceTypeId)

        resourceTypeData = next(
            (
                resourceType
                for resourceType in list(resourceTypesData)
                if resourceType[0] == resourceTypeId
            ),
            None,
        )

        resourceTypeName = resourceTypeData[1]
        resourceTypeDescription = resourceTypeData[2]

        # Customise buttons with resource type name
        generated_template["blocks"][3]["elements"][0]["text"][
            "text"
        ] = f"Add {resourceTypeName} :heavy_plus_sign:"
        generated_template["blocks"][3]["elements"][1]["text"][
            "text"
        ] = f"Modify {resourceTypeName} :pencil:"
        generated_template["blocks"][3]["elements"][2]["text"][
            "text"
        ] = f"Delete {resourceTypeName} ❌"

        # Set the buttons values to the resource type ids
        for i in range(3):
            generated_template["blocks"][3]["elements"][i]["value"] = ",".join(
                [str(resourceTypeId), resourceTypeName]
            )

        environments = database.getEnvironments(organisationId, resourceTypeId)
        # Don't show modify or delete buttons if no environments are defined
        if len(environments) == 0:
            del generated_template["blocks"][3]["elements"][2]
            del generated_template["blocks"][3]["elements"][1]
        generated_template["blocks"] = (
            generated_template["blocks"][:2]
            + views.generate_environment_list(
                environments,
                database.getBookings(
                    organisationId=organisationId, resourceTypeId=resourceTypeId
                ),
            )
            + generated_template["blocks"][2:]
        )

        if resourceTypeDescription:
            generated_template["blocks"].insert(
                1, views.generateResourceTypeDescription(resourceTypeDescription)
            )

    client.views_publish(user_id=userId, view=generated_template)
    return generated_template


@app.event("app_home_opened")
def update_home_tab(client, event, logger):
    try:
        # Try and get userId first as it's needed to display errors
        userId = event["user"]
        teamData = client.team_info().data
        organisationId = teamData["team"]["id"]
        refresh_home_template(organisationId, userId, client)
    except Exception as e:
        logging.error(e)
        print(traceback.format_exc())
        error_template["blocks"][1]["text"]["text"] = str(e)
        client.views_publish(user_id=userId, view=error_template)


@app.action("button-book-clicked")
def handle_book_clicked(ack, body, client):
    organisationId = body["team"]["id"]
    userId = body["user"]["id"]
    resourceTypeId = body["view"]["state"]["values"]\
        ["resourcetype"]["modify-resourcetype-select"]["selected_option"]["value"]
    environmentId = body["actions"][0]["value"]
    environment = database.getEnvironment(environmentId)
    bookings = database.getBookings(organisationId, environmentId, resourceTypeId)
    bookings = utilities.databaseResultToDict(bookings, 1)
    validBookingKeys = utilities.getValidBookings(environment[4], environment[5])
    environment = tuple(environment) + (bookings, validBookingKeys)

    result = book_env_template.render(
        environment=environment,
        resourceTypeId=resourceTypeId,
        userId=userId
    )

    client.views_open(trigger_id=body["trigger_id"], view=result)
    ack()


@app.action("create-booking")
def handle_create_booking(ack, body, client):
    organisationId = body["team"]["id"]
    resourceTypeId = int(body["view"]["private_metadata"])
    environmentId = body["actions"][0]["value"]
    environment = database.getEnvironment(environmentId)
    bookingKey = body["actions"][0]["block_id"]
    userId = body["user"]["id"]
    database.addBooking(
        environmentId, datetime.strptime(bookingKey, "%Y-%m-%d").date(), userId
    )
    print(f"Added booking - {environmentId}, {bookingKey}, {userId}")

    bookings = database.getBookings(organisationId, environmentId, resourceTypeId)
    bookings = utilities.databaseResultToDict(bookings, 1)
    validBookingKeys = utilities.getValidBookings(environment[4], environment[5])
    environment = tuple(environment) + (bookings, validBookingKeys)

    result = book_env_template.render(
        environment=environment,
        resourceTypeId=resourceTypeId,
        userId=userId
    )

    client.views_update(view_id=body["view"]["id"], view=result)
    ack()


@app.action("button-modify-environment")
def action_modify_environment(ack, body, client):
    organisationId = body["team"]["id"]
    resourceTypeId, resourceTypeName = body["actions"][0]["value"].split(",")

    generated_template = copy.deepcopy(modify_enviroment_template)
    generated_template["blocks"][0]["elements"][0][
        "options"
    ] = views.generate_environment_options(
        database.getEnvironments(organisationId, resourceTypeId)
    )
    titleStr = utilities.truncateString(f"Modify {resourceTypeName}")
    generated_template["title"]["text"] = titleStr
    generated_template["private_metadata"] = str(resourceTypeId)

    client.views_open(trigger_id=body["trigger_id"], view=generated_template)
    ack()


# This is the one from the home page
@app.action("modify-resourcetype-select")
def handle_resourcetype_select(ack, body, client):
    organisationId = body["team"]["id"]
    userId = body["user"]["id"]
    resourceTypeId = body["actions"][0]["selected_option"]["value"]

    print(f"Switching to resourceTypeId: {resourceTypeId}")

    # Re-generate the home page
    refresh_home_template(organisationId, userId, client, resourceTypeId)

    ack()


@app.action(re.compile("environment-custom-add-more|environment-custom-remove-last|environment-custom-timepicker-change|booking-type-changed"))
def handle_environment_custom_add_more(ack, body, client):
    bookingType = body["view"]["state"]["values"]["env_booking_type"]["booking-type-changed"]["selected_option"]["value"]
    resourceTypeId = int(body["view"]["private_metadata"])
    resourceTypeName = body["view"]["title"]["text"]
    
    # Timepicker handling
    actionId = body['actions'][0]['action_id']
    bookingTimes = []
    for envKey in body["view"]["state"]["values"].keys():
        if "env_custom_time" in envKey:
            newTime = body["view"]["state"]["values"][envKey]['environment-custom-timepicker-change']['selected_time']
            if newTime in bookingTimes and actionId == "environment-custom-timepicker-change":
                print("Duplicates found!")
                # TODO: This doesn't work currently
                errors = {
                    envKey: "Duplicate times are not allowed"
                }
                ack(response_action="errors", errors=errors)
                return
            bookingTimes.append(newTime)
    if actionId == 'environment-custom-add-more':
        if len(bookingTimes) < 23:
            bookingTimes.append("00:00")
    elif actionId == 'environment-custom-remove-last':
        try:
            bookingTimes.pop()
        except IndexError:
            pass

    result = add_env_template.render(
        data={
            "resourceTypeId": resourceTypeId,
            "resourceTypeName": resourceTypeName,
            "bookingType": bookingType,
        },
        bookingTimes=bookingTimes
    )
    client.views_update(view_id=body["view"]["id"], view=result)
    ack()


@app.action("modify-environment-select")
def handle_modify_environment_select(ack, body, client):
    resourceTypeId = int(body["view"]["private_metadata"])
    organisationId = body["team"]["id"]
    environmentId = body["actions"][0]["selected_option"]["value"]
    environmentName = body["actions"][0]["selected_option"]["text"]["text"]

    logging.info(f"Modifying environment {environmentId}:{environmentName}")

    generated_template = copy.deepcopy(modify_enviroment_template)
    generated_template["title"]["text"] = body["view"]["title"]["text"]
    generated_template["private_metadata"] = str(resourceTypeId)
    generated_template["blocks"][0]["elements"][0]["initial_option"] = body["actions"][
        0
    ]["selected_option"]
    generated_template["blocks"][0]["elements"][0][
        "options"
    ] = views.generate_environment_options(
        database.getEnvironments(organisationId, resourceTypeId)
    )
    generated_template["blocks"] += views.generateModifyEnvironment(
        database.getEnvironment(environmentId)
    )

    client.views_update(view_id=body["view"]["id"], view=generated_template)
    ack()


@app.action("remove-booking")
def handle_remove_booking(ack, body, client):
    organisationId = body["team"]["id"]
    resourceTypeId = int(body["view"]["private_metadata"])
    bookingKey = body["actions"][0]["block_id"]
    environmentId = body["actions"][0]["value"]
    environment = database.getEnvironment(environmentId)
    userId = body["user"]["id"]
    database.removeBooking(
        environmentId, bookingKey, userId
    )
    print(f"Removed booking - {environmentId}, {bookingKey}, {userId}")

    bookings = database.getBookings(organisationId, environmentId, resourceTypeId)
    bookings = utilities.databaseResultToDict(bookings, 1)
    validBookingKeys = utilities.getValidBookings(environment[4], environment[5])
    environment = tuple(environment) + (bookings, validBookingKeys)

    result = book_env_template.render(
        environment=environment,
        resourceTypeId=resourceTypeId,
        userId=userId
    )

    client.views_update(view_id=body["view"]["id"], view=result)
    ack()


@app.action("button-add-environment")
def handle_add_env_clicked(ack, body, client):
    resourceTypeId, resourceTypeName = body["actions"][0]["value"].split(",")
    result = add_env_template.render(
        data={
            "resourceTypeId": resourceTypeId,
            "resourceTypeName": resourceTypeName,
            "bookingType": "DAILY",
        }
    )
    client.views_open(trigger_id=body["trigger_id"], view=result)
    ack()


@app.action("button-delete-environment")
def handle_delete_env_clicked(ack, body, client):
    organisationId = body["team"]["id"]
    resourceTypeId, resourceTypeName = body["actions"][0]["value"].split(",")

    generated_template = copy.deepcopy(delete_enviroment_template)
    generated_template["private_metadata"] = str(resourceTypeId)
    titleStr = utilities.truncateString(f"Delete {resourceTypeName}")
    generated_template["title"]["text"] = titleStr
    generated_template["blocks"][0]["element"][
        "options"
    ] = views.generate_environment_options(
        database.getEnvironments(organisationId, resourceTypeId)
    )
    client.views_open(trigger_id=body["trigger_id"], view=generated_template)
    ack()


@app.action("button-back")
def handle_back_clicked(ack, body, client):
    userId = body["user"]["id"]
    teamData = client.team_info().data
    organisationId = teamData["team"]["id"]
    refresh_home_template(organisationId, userId, client)
    ack()


@app.action("button-manage-settings")
def handle_settings_clicked(ack, body, client):
    organisationId = body["team"]["id"]
    resourceTypes = list(database.getResourceTypes(organisationId))
    result = manage_settings_template.render(data={"resourceTypes": resourceTypes})
    client.views_update(view_id=body["view"]["id"], view=result)
    ack()


@app.action("button-add-resourcetype")
def handle_add_resourcetype_clicked(ack, body, client):
    userId = body["user"]["id"]
    result = add_resource_type_template.render(
        userId=userId
    )
    client.views_open(trigger_id=body["trigger_id"], view=result)
    ack()

@app.action("button-modify-resourcetype")
def handle_modify_resourcetype_clicked(ack, body, client):
    organisationId = body["team"]["id"]
    resourceTypes = list(database.getResourceTypes(organisationId))
    result = modify_resource_type_template.render(
        resourceTypes=resourceTypes,
        currentResourceType=resourceTypes[0] # Default to first element
    )
    client.views_open(trigger_id=body["trigger_id"], view=result)
    ack()

@app.action("button-delete-resourcetype")
def handle_delete_resourcetype_clicked(ack, body, client):
    organisationId = body["team"]["id"]
    resourceTypes = list(database.getResourceTypes(organisationId))
    result = delete_resource_type_template.render(
        resourceTypes=resourceTypes,
        currentResourceType=resourceTypes[0] # Default to first element
    )
    client.views_open(trigger_id=body["trigger_id"], view=result)
    ack()

@app.action("modify-modal-resourcetype-select")
def handle_modify_resourcetype_select(ack, body, client):
    organisationId = body["team"]["id"]
    resourceTypeId = int(body["view"]["state"]["values"]["resourcetype_id"]["modify-modal-resourcetype-select"]["selected_option"]["value"])
    resourceTypes = list(database.getResourceTypes(organisationId))
    currentResourceType = next(
        (
            resourceType
            for resourceType in resourceTypes
            if resourceType[0] == resourceTypeId
        ),
        None,
    )
    print(f"Switching to {currentResourceType[1]}")

    result = modify_resource_type_template.render(
        resourceTypes=resourceTypes,
        currentResourceType=currentResourceType,
        blockIdSuffix = str(uuid.uuid4()) # Randomise block_ids to get around slack re-rendering bug
    )

    client.views_update(view_id=body["view"]["id"], view=result)
    ack()

@app.view("add-environment")
def handle_add_environment(ack, body, client, view, logger):
    resourceTypeId = int(body["view"]["private_metadata"])
    organisationId = body["team"]["id"]
    userId = body["user"]["id"]
    stateData = body["view"]["state"]["values"]
    newEnvironment = stateData["env_name"]["plain_text_input-action"]["value"]
    description = stateData["env_desc"]["plain_text_input-action"]["value"]
    bookingType = stateData["env_booking_type"]["booking-type-changed"][
        "selected_option"
    ]["value"]
    numberUsers = int(stateData["env_num_users"]["number_input-action"]["value"])
    booking_settings = {}
    if bookingType == "DAILY":
        booking_settings = {
            "numberDaysAdvance": int(
                stateData["env_num_days"]["number_input-action"]["value"]
            )
        }
    elif bookingType == "ONE-OFF":
        booking_settings = {
            "date": stateData["env_oneoff_date"]["datepicker-action"]["selected_date"]
        }
    
    try:
        # Hard-coding resource type temporarily
        database.addEnvironment(
            newEnvironment,
            resourceTypeId,
            bookingType,
            booking_settings,
            numberUsers,
            description=description,
        )
    except Exception as e:
        pprint(e)
        errors = {}
        errors["env_name"] = f"Environment {newEnvironment} already exists"
        ack(response_action="errors", errors=errors)

    # Re-generate the home page
    refresh_home_template(organisationId, userId, client, resourceTypeId)

    ack(response_action="clear")


@app.view("delete-environment")
def handle_delete_environment(ack, body, client, view, logger):
    organisationId = body["team"]["id"]
    userId = body["user"]["id"]
    resourceTypeId = int(body["view"]["private_metadata"])

    delEnvironment = body["view"]["state"]["values"]["env_name"][
        "static_select-action"
    ]["selected_option"]["value"]
    logging.info(f"Trying to delete environment {delEnvironment}")
    database.deleteEnvironment(delEnvironment)

    # Re-generate the home page
    refresh_home_template(organisationId, userId, client, resourceTypeId)

    ack(response_action="clear")


@app.view("add-booking")
def handle_add_booking(ack, body, client, view, logger):
    organisationId = body["team"]["id"]
    userId = body["user"]["id"]
    resourceTypeId = int(body["view"]["private_metadata"])

    # Re-generate the home page
    refresh_home_template(organisationId, userId, client, resourceTypeId)

    ack(response_action="clear")


@app.view("modify-environment")
def handle_modify_environment(ack, body, client, view, logger):
    organisationId = body["team"]["id"]
    userId = body["user"]["id"]
    resourceTypeId = int(body["view"]["private_metadata"])

    # Extract name and description keys
    filtered_env_name = filter(
        lambda x: "env_name_" in x, body["view"]["state"]["values"].keys()
    )
    env_name_key = list(filtered_env_name)[0]
    filtered_env_description = filter(
        lambda x: "env_description_" in x, body["view"]["state"]["values"].keys()
    )
    env_description_key = list(filtered_env_description)[0]

    environmentId = body["view"]["state"]["values"]["env_id"][
        "modify-environment-select"
    ]["selected_option"]["value"]
    environmentName = body["view"]["state"]["values"][env_name_key][
        "plain_text_input-action"
    ]["value"]
    environmentDescription = body["view"]["state"]["values"][env_description_key][
        "plain_text_input-action"
    ]["value"]

    database.modifyEnvironment(environmentId, environmentName, environmentDescription)

    # Re-generate the home page
    refresh_home_template(organisationId, userId, client, resourceTypeId)

    ack(response_action="clear")


@app.view("add-resource-type")
def handle_add_resource_type(ack, body, client, view, logger):
    userId = body["user"]["id"]
    organisationId = body["team"]["id"]
    resourceTypeName = body["view"]["state"]["values"]["resourcetype_name"][
        "plain_text_input-action"
    ]["value"]
    resourceTypeDesc = body["view"]["state"]["values"]["resourcetype_desc"][
        "plain_text_input-action"
    ]["value"]
    resourceTypeAdministrators = body["view"]["state"]["values"]["resourcetype_admins"]["multi_users_select-action"]["selected_users"]
    if len(resourceTypeAdministrators) == 0:
        print("Adding current user as default administrator")
        resourceTypeAdministrators.append(userId)
    
    database.addResourceType(resourceTypeName, organisationId, resourceTypeDesc, resourceTypeAdministrators)
    print(f"Added resourceType {resourceTypeName}")

    resourceTypes = list(database.getResourceTypes(organisationId))
    result = manage_settings_template.render(data={"resourceTypes": resourceTypes})

    client.views_publish(user_id=userId, view=result)
    ack(response_action="clear")

@app.view("modify-resource-type")
def handle_modify_resource_type(ack, body, client, view, logger):
    userId = body["user"]["id"]

    organisationId = body["team"]["id"]
    stateData = body["view"]["state"]["values"]
    # Extract the random block id
    block_id = utilities.extractBlockIdString(stateData, "resourcetype_name_")
    resourceTypeId = int(body["view"]["private_metadata"])
    resourceTypeName = stateData[f"resourcetype_name_{block_id}"]["plain_text_input-action"]["value"]
    resourceTypeDesc = stateData[f"resourcetype_desc_{block_id}"]["plain_text_input-action"]["value"]
    resourceTypeAdministrators = stateData[f"resourcetype_admins_{block_id}"]["multi_users_select-action"]["selected_users"]
    if len(resourceTypeAdministrators) == 0:
        print("Adding current user as default administrator")
        resourceTypeAdministrators.append(userId)
    database.modifyResourceType(resourceTypeId, resourceTypeName, resourceTypeDesc, resourceTypeAdministrators)
    print(f"Modified resourceType {resourceTypeId}")

    resourceTypes = list(database.getResourceTypes(organisationId))
    result = manage_settings_template.render(data={"resourceTypes": resourceTypes})
    client.views_publish(user_id=userId, view=result)

    ack(response_action="clear")

@app.view("delete-resource-type")
def handle_delete_resource_type(ack, body, client, view, logger):
    organisationId = body["team"]["id"]
    stateData = body["view"]["state"]["values"]
    resourceTypeId = int(stateData["resourcetype_name"]["static_select-action"]["selected_option"]["value"])
    database.deleteResourceType(resourceTypeId)
    print(f"Deleted resourceType {resourceTypeId}")
    resourceTypes = list(database.getResourceTypes(organisationId))

    result = manage_settings_template.render(data={"resourceTypes": resourceTypes})
    userId = body["user"]["id"]
    client.views_publish(user_id=userId, view=result)
    ack(response_action="clear")

# Start your app
if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_SOCKET_TOKEN"]).connect()
    app.start(3000)
