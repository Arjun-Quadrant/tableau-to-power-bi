document.addEventListener("DOMContentLoaded", function () {
    const migrationForm = document.getElementById("migrationForm");
    const uploadButton = document.getElementById("uploadButton");
    const reportButton = document.getElementById("reportButton");
    const loaderOverlay = document.getElementById("loader-overlay");
    const popupOverlay = document.getElementById("popup-overlay");
    const popupMessage = document.getElementById("popup-message");

    if (migrationForm) {
        migrationForm.addEventListener("submit", function (event) {
            event.preventDefault();
            loaderOverlay.style.display = "flex";
            disableForm(true);

            const username = document.getElementById("username").value;
            const password = document.getElementById("password").value;

            // Prepare data to send
            const formData = new FormData();
            formData.append("username", username);
            formData.append("password", password);
            
            fetch("/migrate", {
                method: "POST",
                body: formData
            })
                .then(response => response.json())
                .then(data => {
                    loaderOverlay.style.display = "none";
                    disableForm(false);
                    showPopup(data.message || "An error occurred: " + data.error);
                })
                .catch(error => {
                    loaderOverlay.style.display = "none";
                    disableForm(false);
                    showPopup("An error occurred: " + error.message);
                });
        });
    }

    if (uploadButton) {
        uploadButton.addEventListener("click", function (event) {
            event.preventDefault();
            loaderOverlay.style.display = "flex";

            fetch("/upload/start", { method: "GET" })
                .then(response => response.json())
                .then(data => {
                    loaderOverlay.style.display = "none";
                    showPopup(data.message || "An error occurred: " + data.error);
                })
                .catch(error => {
                    loaderOverlay.style.display = "none";
                    showPopup("An error occurred: " + error.message);
                });
        });
    }

    if (reportButton) {
        reportButton.addEventListener("click", function (event) {
            event.preventDefault();
            loaderOverlay.style.display = "flex";

            fetch("/report/get", { method: "GET" })
                .then(response => response.json())
                .then(data => {
                    loaderOverlay.style.display = "none";
                    showPopup(data.message || "An error occurred: " + data.error);
                })
                .catch(error => {
                    loaderOverlay.style.display = "none";
                    showPopup("An error occurred: " + error.message);
                });
        });
    }

    function disableForm(disable) {
        const formElements = document.querySelectorAll("#migrationForm input, #migrationForm button");
        formElements.forEach(element => {
            element.disabled = disable;
        });
    }

    function showPopup(message) {
        popupMessage.innerText = message;
        popupOverlay.style.display = "flex";
    }

    window.closePopup = function () {
        popupOverlay.style.display = "none";
    };
});