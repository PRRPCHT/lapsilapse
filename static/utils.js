/**
 * Disables the field in parameter and returns its value.
 * @param {string} fieldName The name of the field to handle.
 * @return {string} the value of the field.
 */
function getAndDisable(fieldName) {
    let field = document.getElementById(fieldName);
    field.setAttribute("disabled", "true");
    return field.value;
}

/**
 * Returns the value of the field in parameter.
 * @param {string} fieldName The name of the field to handle.
 * @return {string} The value of the field.
 */
function getValue(fieldName) {
    return document.getElementById(fieldName).value;
}

/**
 * Returns the int value of the field in parameter.
 * @param {string} fieldName The name of the field to handle.
 * @return {int} The int value of the field.
 */
function getIntValue(fieldName) {
    return parseInt(getValue(fieldName));
}

/**
 * Enables a field that has been disabled.
 * @param {string} fieldName The name of the field to enable.
 */
function enable(fieldName) {
    document.getElementById(fieldName).removeAttribute("disabled");
}

/**
 * Disables a field that has been enabled.
 * @param {string} fieldName The name of the field to disable.
 */
function disable(fieldName) {
    document.getElementById(fieldName).setAttribute("disabled", "true");
}

/**
 * Clears the error style for a field.
 * @param {string} fieldName The name of the field to handle.
 */
function clearFieldInError(fieldName) {
    document.getElementById(fieldName).classList.remove("border-danger-subtle", "bg-danger-subtle", "text-danger-emphasis");
}

/**
 * Sets the error style for a field.
 * @param {string} fieldName The name of the field to handle.
 */
function fieldInError(fieldName) {
    document.getElementById(fieldName).classList.add("border-danger-subtle", "bg-danger-subtle", "text-danger-emphasis");
}

/**
 * Handles the click on the delete button.
 * @param {string} elementID The thumbnail's data.
 */
async function deletePhoto(elementID) {
    let body = { name: elementID };
    let resp = await fetch("/deletephoto", {
        method: "POST",
        body: JSON.stringify(body),
    });
    let res = await resp.json();
    if (res.error) {
        document.getElementById(elementID + "_error").classList.replace("d-none", "d-block");
        return false;
    } else {
        try {
            document.getElementById(elementID + "_card").remove();
        } catch (error) {
            console.log("The photo has already been deleted");
        }
        return true;
    }
}


/**
 * Handles the click on the delete button.
 * @param {string} elementID The timelapse's data.
 */
async function deleteTimelapse(elementID) {
    let body = { timelapse: elementID };
    let resp = await fetch("/deletetimelapse", {
        method: "POST",
        body: JSON.stringify(body),
    });
    console.log(resp)
    let res = await resp.json();
    if (res.error) {
        document.getElementById(elementID + "_error").classList.replace("d-none", "d-block");
        return false;
    } else {
        try {
            document.getElementById(elementID + "_card").remove();
        } catch (error) {
            console.log("The timelapse has already been deleted");
        }
        return true;
    }
}