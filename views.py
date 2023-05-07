import copy
import uuid

import utilities

ENVIRONMENT_HEADER = {
    "type": "header",
    "text": {"type": "plain_text", "text": "undefined"},
}

ENVIRONMENT_SECTION = {
    "type": "section",
    "text": {"type": "mrkdwn", "text": ""},
    "accessory": {
        "type": "button",
        "text": {"type": "plain_text", "text": "Book", "emoji": True},
        "value": "undefined",
        "action_id": "button-book-clicked",
    },
}


def generateBookingStr(date, environmentId, bookings):
    bookingStr = ""
    booking = list(
        filter(lambda x: x[0] == int(environmentId) and x[1] == date, bookings)
    )
    if len(booking) > 0:
        bookingStr += f"- {str(date)} - Booked by <@{booking[0][2]}>\n"
    else:
        bookingStr += f"- {str(date)} - :sailboat: Free\n"
    return bookingStr


def generate_booking_list(environmentId, bookings, userId):
    GENERATED_MARKUP = []
    valid_dates = utilities.getNextNDays(2)
    for date in valid_dates:
        bookingStr = generateBookingStr(date, environmentId, bookings)
        booking = list(
            filter(lambda x: x[0] == int(environmentId) and x[1] == date, bookings)
        )
        if len(booking) > 0:
            if booking[0][2] == userId:
                GENERATED_MARKUP.append(
                    {
                        "type": "section",
                        "block_id": f"{str(date)}",
                        "text": {"type": "mrkdwn", "text": bookingStr},
                        "accessory": {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Remove Booking",
                                "emoji": True,
                            },
                            "value": f"{str(environmentId)}",
                            "action_id": "remove-booking",
                        },
                    }
                )
            else:
                GENERATED_MARKUP.append(
                    {
                        "type": "section",
                        "block_id": f"booking-section-{str(date)}",
                        "text": {"type": "mrkdwn", "text": bookingStr},
                    }
                )
        else:
            GENERATED_MARKUP.append(
                {
                    "type": "section",
                    "block_id": f"{str(date)}",
                    "text": {"type": "mrkdwn", "text": bookingStr},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Book", "emoji": True},
                        "value": f"{str(environmentId)}",
                        "action_id": "create-booking",
                    },
                }
            )
    return GENERATED_MARKUP


def generate_environment_options(environments):
    GENERATED_MARKUP = []
    for environment in environments:
        GENERATED_MARKUP.append(
            {
                "text": {"type": "plain_text", "text": environment[1], "emoji": True},
                "value": str(environment[0]),
            }
        )
    return GENERATED_MARKUP


def generate_environment_list(environments, bookings):
    GENERATED_MARKUP = []
    for environment in environments:
        newHeaderSection = copy.deepcopy(ENVIRONMENT_HEADER)
        newHeaderSection["text"]["text"] = f"# {environment[1]}"
        GENERATED_MARKUP.append(newHeaderSection)

        newEnvironmentSection = copy.deepcopy(ENVIRONMENT_SECTION)

        valid_dates = utilities.getNextNDays(2)
        bookingStr = ""
        # If defined as description test for environment
        if environment[2]:
            bookingStr += f"{environment[2]}\n\n"

        for date in valid_dates:
            bookingStr += generateBookingStr(date, environment[0], bookings)

        newEnvironmentSection["text"]["text"] = bookingStr
        newEnvironmentSection["accessory"]["text"]["text"] = f"Book {environment[1]}"
        newEnvironmentSection["accessory"]["value"] = str(environment[0])
        GENERATED_MARKUP.append(newEnvironmentSection)

    return GENERATED_MARKUP


MODIFY_ENVIRONMENT_SECTION = [
    {"type": "divider"},
    {
        "type": "input",
        "block_id": "env_name",
        "element": {"type": "plain_text_input", "action_id": "plain_text_input-action"},
        "label": {"type": "plain_text", "text": "Name", "emoji": True},
    },
    {
        "type": "input",
        "block_id": "env_description",
        "optional": True,
        "element": {
            "type": "plain_text_input",
            "multiline": True,
            "action_id": "plain_text_input-action",
        },
        "label": {"type": "plain_text", "text": "Description", "emoji": True},
    },
]


def generateModifyEnvironment(environment):
    newEnvironmentSection = copy.deepcopy(MODIFY_ENVIRONMENT_SECTION)
    newEnvironmentSection[1]["element"]["initial_value"] = environment[1]
    if environment[2]:
        newEnvironmentSection[2]["element"]["initial_value"] = environment[2]
    
    # There appears to be known issues with Slack re-rendering
    # https://github.com/slackapi/bolt-js/issues/1073#issuecomment-903599111
    block_id_suffix = str(uuid.uuid4())
    newEnvironmentSection[1]["block_id"] = f"env_name_{block_id_suffix}"
    newEnvironmentSection[2]["block_id"] = f"env_description_{block_id_suffix}"

    return newEnvironmentSection


def generateResourceTypesText(resourceTypes):
    outputStr = ""
    for resource in list(resourceTypes):
        outputStr += f"- *{resource[1]}*\n"
    return outputStr

def generateResourceTypeDescription(descriptionText):
    return {
        "type": "context",
        "elements": [
            {
                "type": "plain_text",
                "text": descriptionText,
                "emoji": True
            }
        ]
    }