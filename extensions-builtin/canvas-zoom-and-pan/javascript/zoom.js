onUiLoaded(async() => {
    const elementIDs = {
        img2imgTabs: "#mode_img2img .tab-nav",
        inpaint: "#img2maskimg",
        inpaintSketch: "#inpaint_sketch",
        rangeGroup: "#img2img_column_size",
        sketch: "#img2img_sketch"
    };
    const tabNameToElementId = {
        "Inpaint sketch": elementIDs.inpaintSketch,
        "Inpaint": elementIDs.inpaint,
        "Sketch": elementIDs.sketch
    };


    // Helper functions
    // Get active tab

    /**
     * Waits for an element to be present in the DOM.
     */
    const waitForElement = (id) => new Promise(resolve => {
        const checkForElement = () => {
            const element = document.querySelector(id);
            if (element) return resolve(element);
            setTimeout(checkForElement, 100);
        };
        checkForElement();
    });

    function getActiveTab(elements, all = false) {
        if (!elements.img2imgTabs) return null;
        const tabs = elements.img2imgTabs.querySelectorAll("button");

        if (all) return tabs;

        for (let tab of tabs) {
            if (tab.classList.contains("selected")) {
                return tab;
            }
        }
    }

    // Get tab ID
    function getTabId(elements) {
        const activeTab = getActiveTab(elements);
        if (!activeTab) return null;
        return tabNameToElementId[activeTab.innerText];
    }

    // Wait until opts loaded
    async function waitForOpts() {
        for (; ;) {
            if (window.opts && Object.keys(window.opts).length) {
                return window.opts;
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }

    // Detect whether the element has a horizontal scroll bar
    function hasHorizontalScrollbar(element) {
        return element.scrollWidth > element.clientWidth;
    }

    // Function for defining the "Ctrl", "Shift" and "Alt" keys
    function isModifierKey(event, key) {
        switch (key) {
        case "Ctrl":
            return event.ctrlKey;
        case "Shift":
            return event.shiftKey;
        case "Alt":
            return event.altKey;
        default:
            return false;
        }
    }

    // Check if hotkey is valid
    function isValidHotkey(value) {
        const specialKeys = ["Ctrl", "Alt", "Shift", "Disable"];
        return (
            (typeof value === "string" &&
                value.length === 1 &&
                /[a-z]/i.test(value)) ||
            specialKeys.includes(value)
        );
    }

    // Normalize hotkey
    function normalizeHotkey(hotkey) {
        return hotkey.length === 1 ? "Key" + hotkey.toUpperCase() : hotkey;
    }

    // Format hotkey for display
    function formatHotkeyForDisplay(hotkey) {
        return hotkey.startsWith("Key") ? hotkey.slice(3) : hotkey;
    }

    // Create hotkey configuration with the provided options
    function createHotkeyConfig(defaultHotkeysConfig, hotkeysConfigOpts) {
        const result = {}; // Resulting hotkey configuration
        const usedKeys = new Set(); // Set of used hotkeys

        // Iterate through defaultHotkeysConfig keys
        for (const key in defaultHotkeysConfig) {
            const userValue = hotkeysConfigOpts[key]; // User-provided hotkey value
            const defaultValue = defaultHotkeysConfig[key]; // Default hotkey value

            // Apply appropriate value for undefined, boolean, or object userValue
            if (
                userValue === undefined ||
                typeof userValue === "boolean" ||
                typeof userValue === "object" ||
                userValue === "disable"
            ) {
                result[key] =
                    userValue === undefined ? defaultValue : userValue;
            } else if (isValidHotkey(userValue)) {
                const normalizedUserValue = normalizeHotkey(userValue);

                // Check for conflicting hotkeys
                if (!usedKeys.has(normalizedUserValue)) {
                    usedKeys.add(normalizedUserValue);
                    result[key] = normalizedUserValue;
                } else {
                    console.error(
                        `Hotkey: ${formatHotkeyForDisplay(
                            userValue
                        )} for ${key} is repeated and conflicts with another hotkey. The default hotkey is used: ${formatHotkeyForDisplay(
                            defaultValue
                        )}`
                    );
                    result[key] = defaultValue;
                }
            } else {
                console.error(
                    `Hotkey: ${formatHotkeyForDisplay(
                        userValue
                    )} for ${key} is not valid. The default hotkey is used: ${formatHotkeyForDisplay(
                        defaultValue
                    )}`
                );
                result[key] = defaultValue;
            }
        }

        return result;
    }

    // Disables functions in the config object based on the provided list of function names
    function disableFunctions(config, disabledFunctions) {
        // Bind the hasOwnProperty method to the functionMap object to avoid errors
        const hasOwnProperty =
            Object.prototype.hasOwnProperty.bind(functionMap);

        // Loop through the disabledFunctions array and disable the corresponding functions in the config object
        disabledFunctions.forEach(funcName => {
            if (hasOwnProperty(funcName)) {
                const key = functionMap[funcName];
                config[key] = "disable";
            }
        });

        // Return the updated config object
        return config;
    }

    /**
     * The restoreImgRedMask function displays a red mask around an image to indicate the aspect ratio.
     * If the image display property is set to 'none', the mask breaks. To fix this, the function
     * temporarily sets the display property to 'block' and then hides the mask again after 300 milliseconds
     * to avoid breaking the canvas. Additionally, the function adjusts the mask to work correctly on
     * very long images.
     */
    function restoreImgRedMask(elements) {
        const mainTabId = getTabId(elements);

        if (!mainTabId) return;

        const mainTab = gradioApp().querySelector(mainTabId);
        const img = mainTab.querySelector("img");
        const imageARPreview = gradioApp().querySelector("#imageARPreview");

        if (!img || !imageARPreview) return;

        imageARPreview.style.transform = "";
        if (parseFloat(mainTab.style.width) > 865) {
            const transformString = mainTab.style.transform;
            const scaleMatch = transformString.match(
                /scale\(([-+]?[0-9]*\.?[0-9]+)\)/
            );
            let zoom = 1; // default zoom

            if (scaleMatch && scaleMatch[1]) {
                zoom = Number(scaleMatch[1]);
            }

            imageARPreview.style.transformOrigin = "0 0";
            imageARPreview.style.transform = `scale(${zoom})`;
        }

        if (img.style.display !== "none") return;

        img.style.display = "block";

        setTimeout(() => {
            img.style.display = "none";
        }, 400);
    }

    const hotkeysConfigOpts = await waitForOpts();

    // Default config
    const defaultHotkeysConfig = {
        canvas_hotkey_zoom: "Alt",
        canvas_hotkey_adjust: "Ctrl",
        canvas_hotkey_reset: "KeyR",
        canvas_hotkey_fullscreen: "KeyS",
        canvas_hotkey_move: "KeyF",
        canvas_hotkey_overlap: "KeyO",
        canvas_hotkey_shrink_brush: "KeyQ",
        canvas_hotkey_grow_brush: "KeyW",
        canvas_disabled_functions: [],
        canvas_show_tooltip: true,
        canvas_auto_expand: true,
        canvas_blur_prompt: false,
    };

    const functionMap = {
        "Zoom": "canvas_hotkey_zoom",
        "Adjust brush size": "canvas_hotkey_adjust",
        "Hotkey shrink brush": "canvas_hotkey_shrink_brush",
        "Hotkey enlarge brush": "canvas_hotkey_grow_brush",
        "Moving canvas": "canvas_hotkey_move",
        "Fullscreen": "canvas_hotkey_fullscreen",
        "Reset Zoom": "canvas_hotkey_reset",
        "Overlap": "canvas_hotkey_overlap"
    };

    // Loading the configuration from opts
    const preHotkeysConfig = createHotkeyConfig(
        defaultHotkeysConfig,
        hotkeysConfigOpts
    );

    // Disable functions that are not needed by the user
    const hotkeysConfig = disableFunctions(
        preHotkeysConfig,
        preHotkeysConfig.canvas_disabled_functions
    );

    let isMoving = false;
    let mouseX, mouseY;
    let activeElement;
    let interactedWithAltKey = false;

    const elements = Object.fromEntries(
        Object.keys(elementIDs).map(id => [
            id,
            gradioApp().querySelector(elementIDs[id])
        ])
    );
    const elemData = {};

    // Apply functionality to the range inputs. Restore redmask and correct for long images.
    const rangeInputs = elements.rangeGroup ?
        Array.from(elements.rangeGroup.querySelectorAll("input")) :
        [
            gradioApp().querySelector("#img2img_width input[type='range']"),
            gradioApp().querySelector("#img2img_height input[type='range']")
        ];

    for (const input of rangeInputs) {
        input?.addEventListener("input", () => restoreImgRedMask(elements));
    }

    function applyZoomAndPan(elemId, isExtension = true) {
        const targetElement = gradioApp().querySelector(elemId);

        if (!targetElement) {
            console.log("Element not found", elemId);
            return;
        }

        targetElement.style.transformOrigin = "0 0";

        elemData[elemId] = {
            zoom: 1,
            panX: 0,
            panY: 0
        };
        let fullScreenMode = false;

        // Create tooltip
        function createTooltip() {
            const toolTipElement =
                targetElement.querySelector(".image-container");
            const tooltip = document.createElement("div");
            tooltip.className = "canvas-tooltip";

            // Creating an item of information
            const info = document.createElement("i");
            info.className = "canvas-tooltip-info";
            info.textContent = "";

            // Create a container for the contents of the tooltip
            const tooltipContent = document.createElement("div");
            tooltipContent.className = "canvas-tooltip-content";

            // Define an array with hotkey information and their actions
            const hotkeysInfo = [
                {
                    configKey: "canvas_hotkey_zoom",
                    action: "Zoom canvas",
                    keySuffix: " + wheel"
                },
                {
                    configKey: "canvas_hotkey_adjust",
                    action: "Adjust brush size",
                    keySuffix: " + wheel"
                },
                {configKey: "canvas_hotkey_reset", action: "Reset zoom"},
                {
                    configKey: "canvas_hotkey_fullscreen",
                    action: "Fullscreen mode"
                },
                {configKey: "canvas_hotkey_move", action: "Move canvas"},
                {configKey: "canvas_hotkey_overlap", action: "Overlap"}
            ];

            // Create hotkeys array with disabled property based on the config values
            const hotkeys = hotkeysInfo.map(info => {
                const configValue = hotkeysConfig[info.configKey];
                const key = info.keySuffix ?
                    `${configValue}${info.keySuffix}` :
                    configValue.charAt(configValue.length - 1);
                return {
                    key,
                    action: info.action,
                    disabled: configValue === "disable"
                };
            });

            for (const hotkey of hotkeys) {
                if (hotkey.disabled) {
                    continue;
                }

                const p = document.createElement("p");
                p.innerHTML = `<b>${hotkey.key}</b> - ${hotkey.action}`;
                tooltipContent.appendChild(p);
            }

            // Add information and content elements to the tooltip element
            tooltip.appendChild(info);
            tooltip.appendChild(tooltipContent);

            // Add a hint element to the target element
            toolTipElement.appendChild(tooltip);
        }

        //Show tool tip if setting enable
        if (hotkeysConfig.canvas_show_tooltip) {
            createTooltip();
        }

        // In the course of research, it was found that the tag img is very harmful when zooming and creates white canvases. This hack allows you to almost never think about this problem, it has no effect on webui.
        function fixCanvas() {
            const activeTab = getActiveTab(elements)?.textContent.trim();

            if (activeTab && activeTab !== "img2img") {
                const img = targetElement.querySelector(`${elemId} img`);

                if (img && img.style.display !== "none") {
                    img.style.display = "none";
                    img.style.visibility = "hidden";
                }
            }
        }

        // Reset the zoom level and pan position of the target element to their initial values
        function resetZoom() {
            elemData[elemId] = {
                zoomLevel: 1,
                panX: 0,
                panY: 0
            };

            if (isExtension) {
                targetElement.style.overflow = "hidden";
            }

            targetElement.isZoomed = false;

            fixCanvas();
            targetElement.style.transform = `scale(${elemData[elemId].zoomLevel}) translate(${elemData[elemId].panX}px, ${elemData[elemId].panY}px)`;

            const canvas = gradioApp().querySelector(
                `${elemId} canvas[key="interface"]`
            );

            toggleOverlap("off");
            fullScreenMode = false;

            const closeBtn = targetElement.querySelector("button[aria-label='Remove Image']");
            if (closeBtn) {
                closeBtn.addEventListener("click", resetZoom);
            }

            if (canvas && isExtension) {
                const parentElement = targetElement.closest('[id^="component-"]');
                if (
                    canvas &&
                    parseFloat(canvas.style.width) > parentElement.offsetWidth &&
                    parseFloat(targetElement.style.width) > parentElement.offsetWidth
                ) {
                    fitToElement();
                    return;
                }

            }

            if (
                canvas &&
                !isExtension &&
                parseFloat(canvas.style.width) > 865 &&
                parseFloat(targetElement.style.width) > 865
            ) {
                fitToElement();
                return;
            }

            targetElement.style.width = "";
        }

        // Toggle the zIndex of the target element between two values, allowing it to overlap or be overlapped by other elements
        function toggleOverlap(forced = "") {
            const zIndex1 = "0";
            const zIndex2 = "998";

            targetElement.style.zIndex =
                targetElement.style.zIndex !== zIndex2 ? zIndex2 : zIndex1;

            if (forced === "off") {
                targetElement.style.zIndex = zIndex1;
            } else if (forced === "on") {
                targetElement.style.zIndex = zIndex2;
            }
        }

        // Adjust the brush size based on the deltaY value from a mouse wheel event
        function adjustBrushSize(
            elemId,
            deltaY,
            withoutValue = false,
            percentage = 5
        ) {
            const input =
                gradioApp().querySelector(
                    `${elemId} input[aria-label='Brush radius']`
                ) ||
                gradioApp().querySelector(
                    `${elemId} button[aria-label="Use brush"]`
                );

            if (input) {
                input.click();
                if (!withoutValue) {
                    const maxValue =
                        parseFloat(input.getAttribute("max")) || 100;
                    const changeAmount = maxValue * (percentage / 100);
                    const newValue =
                        parseFloat(input.value) +
                        (deltaY > 0 ? -changeAmount : changeAmount);
                    input.value = Math.min(Math.max(newValue, 0), maxValue);
                    input.dispatchEvent(new Event("change"));
                }
            }
        }

        // Reset zoom when uploading a new image
        const fileInput = gradioApp().querySelector(
            `${elemId} input[type="file"][accept="image/*"].svelte-116rqfv`
        );
        fileInput.addEventListener("click", resetZoom);

        // Update the zoom level and pan position of the target element based on the values of the zoomLevel, panX and panY variables
        function updateZoom(newZoomLevel, mouseX, mouseY) {
            newZoomLevel = Math.max(0.1, Math.min(newZoomLevel, 15));

            elemData[elemId].panX +=
                mouseX - (mouseX * newZoomLevel) / elemData[elemId].zoomLevel;
            elemData[elemId].panY +=
                mouseY - (mouseY * newZoomLevel) / elemData[elemId].zoomLevel;

            targetElement.style.transformOrigin = "0 0";
            targetElement.style.transform = `translate(${elemData[elemId].panX}px, ${elemData[elemId].panY}px) scale(${newZoomLevel})`;

            toggleOverlap("on");
            if (isExtension) {
                targetElement.style.overflow = "visible";
            }

            return newZoomLevel;
        }

        // Change the zoom level based on user interaction
        function changeZoomLevel(operation, e) {
            if (isModifierKey(e, hotkeysConfig.canvas_hotkey_zoom)) {
                e.preventDefault();

                if (hotkeysConfig.canvas_hotkey_zoom === "Alt") {
                    interactedWithAltKey = true;
                }

                let zoomPosX, zoomPosY;
                let delta = 0.2;
                if (elemData[elemId].zoomLevel > 7) {
                    delta = 0.9;
                } else if (elemData[elemId].zoomLevel > 2) {
                    delta = 0.6;
                }

                zoomPosX = e.clientX;
                zoomPosY = e.clientY;

                fullScreenMode = false;
                elemData[elemId].zoomLevel = updateZoom(
                    elemData[elemId].zoomLevel +
                    (operation === "+" ? delta : -delta),
                    zoomPosX - targetElement.getBoundingClientRect().left,
                    zoomPosY - targetElement.getBoundingClientRect().top
                );

                targetElement.isZoomed = true;
            }
        }

        /**
         * This function fits the target element to the screen by calculating
         * the required scale and offsets. It also updates the global variables
         * zoomLevel, panX, and panY to reflect the new state.
         */

        function fitToElement() {
            //Reset Zoom
            targetElement.style.transform = `translate(${0}px, ${0}px) scale(${1})`;

            let parentElement;

            if (isExtension) {
                parentElement = targetElement.closest('[id^="component-"]');
            } else {
                parentElement = targetElement.parentElement;
            }


            // Get element and screen dimensions
            const elementWidth = targetElement.offsetWidth;
            const elementHeight = targetElement.offsetHeight;

            const screenWidth = parentElement.clientWidth;
            const screenHeight = parentElement.clientHeight;

            // Get element's coordinates relative to the parent element
            const elementRect = targetElement.getBoundingClientRect();
            const parentRect = parentElement.getBoundingClientRect();
            const elementX = elementRect.x - parentRect.x;

            // Calculate scale and offsets
            const scaleX = screenWidth / elementWidth;
            const scaleY = screenHeight / elementHeight;
            const scale = Math.min(scaleX, scaleY);

            const transformOrigin =
                window.getComputedStyle(targetElement).transformOrigin;
            const [originX, originY] = transformOrigin.split(" ");
            const originXValue = parseFloat(originX);
            const originYValue = parseFloat(originY);

            const offsetX =
                (screenWidth - elementWidth * scale) / 2 -
                originXValue * (1 - scale);
            const offsetY =
                (screenHeight - elementHeight * scale) / 2.5 -
                originYValue * (1 - scale);

            // Apply scale and offsets to the element
            targetElement.style.transform = `translate(${offsetX}px, ${offsetY}px) scale(${scale})`;

            // Update global variables
            elemData[elemId].zoomLevel = scale;
            elemData[elemId].panX = offsetX;
            elemData[elemId].panY = offsetY;

            fullScreenMode = false;
            toggleOverlap("off");
        }

        /**
         * This function fits the target element to the screen by calculating
         * the required scale and offsets. It also updates the global variables
         * zoomLevel, panX, and panY to reflect the new state.
         */

        // Fullscreen mode
        function fitToScreen() {
            const canvas = gradioApp().querySelector(
                `${elemId} canvas[key="interface"]`
            );

            if (!canvas) return;

            if (canvas.offsetWidth > 862 || isExtension) {
                targetElement.style.width = (canvas.offsetWidth + 2) + "px";
            }

            if (isExtension) {
                targetElement.style.overflow = "visible";
            }

            if (fullScreenMode) {
                resetZoom();
                fullScreenMode = false;
                return;
            }

            //Reset Zoom
            targetElement.style.transform = `translate(${0}px, ${0}px) scale(${1})`;

            // Get scrollbar width to right-align the image
            const scrollbarWidth =
                window.innerWidth - document.documentElement.clientWidth;

            // Get element and screen dimensions
            const elementWidth = targetElement.offsetWidth;
            const elementHeight = targetElement.offsetHeight;
            const screenWidth = window.innerWidth - scrollbarWidth;
            const screenHeight = window.innerHeight;

            // Get element's coordinates relative to the page
            const elementRect = targetElement.getBoundingClientRect();
            const elementY = elementRect.y;
            const elementX = elementRect.x;

            // Calculate scale and offsets
            const scaleX = screenWidth / elementWidth;
            const scaleY = screenHeight / elementHeight;
            const scale = Math.min(scaleX, scaleY);

            // Get the current transformOrigin
            const computedStyle = window.getComputedStyle(targetElement);
            const transformOrigin = computedStyle.transformOrigin;
            const [originX, originY] = transformOrigin.split(" ");
            const originXValue = parseFloat(originX);
            const originYValue = parseFloat(originY);

            // Calculate offsets with respect to the transformOrigin
            const offsetX =
                (screenWidth - elementWidth * scale) / 2 -
                elementX -
                originXValue * (1 - scale);
            const offsetY =
                (screenHeight - elementHeight * scale) / 2 -
                elementY -
                originYValue * (1 - scale);

            // Apply scale and offsets to the element
            targetElement.style.transform = `translate(${offsetX}px, ${offsetY}px) scale(${scale})`;

            // Update global variables
            elemData[elemId].zoomLevel = scale;
            elemData[elemId].panX = offsetX;
            elemData[elemId].panY = offsetY;

            fullScreenMode = true;
            toggleOverlap("on");
        }

        // Handle keydown events
        function handleKeyDown(event) {
            // Disable key locks to make pasting from the buffer work correctly
            if ((event.ctrlKey && event.code === 'KeyV') || (event.ctrlKey && event.code === 'KeyC') || event.code === "F5") {
                return;
            }

            // before activating shortcut, ensure user is not actively typing in an input field
            if (!hotkeysConfig.canvas_blur_prompt) {
                if (event.target.nodeName === 'TEXTAREA' || event.target.nodeName === 'INPUT') {
                    return;
                }
            }


            const hotkeyActions = {
                [hotkeysConfig.canvas_hotkey_reset]: resetZoom,
                [hotkeysConfig.canvas_hotkey_overlap]: toggleOverlap,
                [hotkeysConfig.canvas_hotkey_fullscreen]: fitToScreen,
                [hotkeysConfig.canvas_hotkey_shrink_brush]: () => adjustBrushSize(elemId, 10),
                [hotkeysConfig.canvas_hotkey_grow_brush]: () => adjustBrushSize(elemId, -10)
            };

            const action = hotkeyActions[event.code];
            if (action) {
                event.preventDefault();
                action(event);
            }

            if (
                isModifierKey(event, hotkeysConfig.canvas_hotkey_zoom) ||
                isModifierKey(event, hotkeysConfig.canvas_hotkey_adjust)
            ) {
                event.preventDefault();
            }
        }

        // Get Mouse position
        function getMousePosition(e) {
            mouseX = e.offsetX;
            mouseY = e.offsetY;
        }

        // Simulation of the function to put a long image into the screen.
        // We detect if an image has a scroll bar or not, make a fullscreen to reveal the image, then reduce it to fit into the element.
        // We hide the image and show it to the user when it is ready.

        targetElement.isExpanded = false;
        function autoExpand() {
            const canvas = document.querySelector(`${elemId} canvas[key="interface"]`);
            if (canvas) {
                if (hasHorizontalScrollbar(targetElement) && targetElement.isExpanded === false) {
                    targetElement.style.visibility = "hidden";
                    setTimeout(() => {
                        fitToScreen();
                        resetZoom();
                        targetElement.style.visibility = "visible";
                        targetElement.isExpanded = true;
                    }, 10);
                }
            }
        }

        targetElement.addEventListener("mousemove", getMousePosition);

        //observers
        // Creating an observer with a callback function to handle DOM changes
        const observer = new MutationObserver((mutationsList, observer) => {
            for (let mutation of mutationsList) {
                // If the style attribute of the canvas has changed, by observation it happens only when the picture changes
                if (mutation.type === 'attributes' && mutation.attributeName === 'style' &&
                    mutation.target.tagName.toLowerCase() === 'canvas') {
                    targetElement.isExpanded = false;
                    setTimeout(resetZoom, 10);
                }
            }
        });

        // Apply auto expand if enabled
        if (hotkeysConfig.canvas_auto_expand) {
            targetElement.addEventListener("mousemove", autoExpand);
            // Set up an observer to track attribute changes
            observer.observe(targetElement, {attributes: true, childList: true, subtree: true});
        }

        // Handle events only inside the targetElement
        let isKeyDownHandlerAttached = false;

        function handleMouseMove() {
            if (!isKeyDownHandlerAttached) {
                document.addEventListener("keydown", handleKeyDown);
                isKeyDownHandlerAttached = true;

                activeElement = elemId;
            }
        }

        function handleMouseLeave() {
            if (isKeyDownHandlerAttached) {
                document.removeEventListener("keydown", handleKeyDown);
                isKeyDownHandlerAttached = false;

                activeElement = null;
            }
        }

        // Add mouse event handlers
        targetElement.addEventListener("mousemove", handleMouseMove);
        targetElement.addEventListener("mouseleave", handleMouseLeave);

        // Reset zoom when click on another tab
        if (elements.img2imgTabs) {
            elements.img2imgTabs.addEventListener("click", resetZoom);
            elements.img2imgTabs.addEventListener("click", () => {
                // targetElement.style.width = "";
                if (parseInt(targetElement.style.width) > 865) {
                    setTimeout(fitToElement, 0);
                }
            });
        }

        targetElement.addEventListener("wheel", e => {
            // change zoom level
            const operation = (e.deltaY || -e.wheelDelta) > 0 ? "-" : "+";
            changeZoomLevel(operation, e);

            // Handle brush size adjustment with ctrl key pressed
            if (isModifierKey(e, hotkeysConfig.canvas_hotkey_adjust)) {
                e.preventDefault();

                if (hotkeysConfig.canvas_hotkey_adjust === "Alt") {
                    interactedWithAltKey = true;
                }

                // Increase or decrease brush size based on scroll direction
                adjustBrushSize(elemId, e.deltaY);
            }
        }, {passive: false});

        // Handle the move event for pan functionality. Updates the panX and panY variables and applies the new transform to the target element.
        function handleMoveKeyDown(e) {

            // Disable key locks to make pasting from the buffer work correctly
            if ((e.ctrlKey && e.code === 'KeyV') || (e.ctrlKey && event.code === 'KeyC') || e.code === "F5") {
                return;
            }

            // before activating shortcut, ensure user is not actively typing in an input field
            if (!hotkeysConfig.canvas_blur_prompt) {
                if (e.target.nodeName === 'TEXTAREA' || e.target.nodeName === 'INPUT') {
                    return;
                }
            }


            if (e.code === hotkeysConfig.canvas_hotkey_move) {
                if (!e.ctrlKey && !e.metaKey && isKeyDownHandlerAttached) {
                    e.preventDefault();
                    document.activeElement.blur();
                    isMoving = true;
                }
            }
        }

        function handleMoveKeyUp(e) {
            if (e.code === hotkeysConfig.canvas_hotkey_move) {
                isMoving = false;
            }
        }

        document.addEventListener("keydown", handleMoveKeyDown);
        document.addEventListener("keyup", handleMoveKeyUp);


        // Prevent firefox from opening main menu when alt is used as a hotkey for zoom or brush size
        function handleAltKeyUp(e) {
            if (e.key !== "Alt" || !interactedWithAltKey) {
                return;
            }

            e.preventDefault();
            interactedWithAltKey = false;
        }

        document.addEventListener("keyup", handleAltKeyUp);


        // Detect zoom level and update the pan speed.
        function updatePanPosition(movementX, movementY) {
            let panSpeed = 2;

            if (elemData[elemId].zoomLevel > 8) {
                panSpeed = 3.5;
            }

            elemData[elemId].panX += movementX * panSpeed;
            elemData[elemId].panY += movementY * panSpeed;

            // Delayed redraw of an element
            requestAnimationFrame(() => {
                targetElement.style.transform = `translate(${elemData[elemId].panX}px, ${elemData[elemId].panY}px) scale(${elemData[elemId].zoomLevel})`;
                toggleOverlap("on");
            });
        }

        function handleMoveByKey(e) {
            if (isMoving && elemId === activeElement) {
                updatePanPosition(e.movementX, e.movementY);
                targetElement.style.pointerEvents = "none";

                if (isExtension) {
                    targetElement.style.overflow = "visible";
                }

            } else {
                targetElement.style.pointerEvents = "auto";
            }
        }

        // Prevents sticking to the mouse
        window.onblur = function() {
            isMoving = false;
        };

        // Checks for extension
        function checkForOutBox() {
            const parentElement = targetElement.closest('[id^="component-"]');
            if (parentElement.offsetWidth < targetElement.offsetWidth && !targetElement.isExpanded) {
                resetZoom();
                targetElement.isExpanded = true;
            }

            if (parentElement.offsetWidth < targetElement.offsetWidth && elemData[elemId].zoomLevel == 1) {
                resetZoom();
            }

            if (parentElement.offsetWidth < targetElement.offsetWidth && targetElement.offsetWidth * elemData[elemId].zoomLevel > parentElement.offsetWidth && elemData[elemId].zoomLevel < 1 && !targetElement.isZoomed) {
                resetZoom();
            }
        }

        if (isExtension) {
            targetElement.addEventListener("mousemove", checkForOutBox);
        }


        window.addEventListener('resize', (e) => {
            resetZoom();

            if (isExtension) {
                targetElement.isExpanded = false;
                targetElement.isZoomed = false;
            }
        });

        gradioApp().addEventListener("mousemove", handleMoveByKey);


    }

    applyZoomAndPan(elementIDs.sketch, false);
    applyZoomAndPan(elementIDs.inpaint, false);
    applyZoomAndPan(elementIDs.inpaintSketch, false);

    // Make the function global so that other extensions can take advantage of this solution
    const applyZoomAndPanIntegration = async(id, elementIDs) => {
        const mainEl = document.querySelector(id);
        if (id.toLocaleLowerCase() === "none") {
            for (const elementID of elementIDs) {
                const el = await waitForElement(elementID);
                if (!el) break;
                applyZoomAndPan(elementID);
            }
            return;
        }

        if (!mainEl) return;
        mainEl.addEventListener("click", async() => {
            for (const elementID of elementIDs) {
                const el = await waitForElement(elementID);
                if (!el) break;
                applyZoomAndPan(elementID);
            }
        }, {once: true});
    };

    window.applyZoomAndPan = applyZoomAndPan; // Only 1 elements, argument elementID, for example applyZoomAndPan("#txt2img_controlnet_ControlNet_input_image")

    window.applyZoomAndPanIntegration = applyZoomAndPanIntegration; // for any extension

    /*
        The function `applyZoomAndPanIntegration` takes two arguments:

        1. `id`: A string identifier for the element to which zoom and pan functionality will be applied on click.
        If the `id` value is "none", the functionality will be applied to all elements specified in the second argument without a click event.

        2. `elementIDs`: An array of string identifiers for elements. Zoom and pan functionality will be applied to each of these elements on click of the element specified by the first argument.
        If "none" is specified in the first argument, the functionality will be applied to each of these elements without a click event.

        Example usage:
        applyZoomAndPanIntegration("#txt2img_controlnet", ["#txt2img_controlnet_ControlNet_input_image"]);
        In this example, zoom and pan functionality will be applied to the element with the identifier "txt2img_controlnet_ControlNet_input_image" upon clicking the element with the identifier "txt2img_controlnet".
    */

    // More examples
    // Add integration with ControlNet txt2img One TAB
    // applyZoomAndPanIntegration("#txt2img_controlnet", ["#txt2img_controlnet_ControlNet_input_image"]);

    // Add integration with ControlNet txt2img Tabs
    // applyZoomAndPanIntegration("#txt2img_controlnet",Array.from({ length: 10 }, (_, i) => `#txt2img_controlnet_ControlNet-${i}_input_image`));

    // Add integration with Inpaint Anything
    // applyZoomAndPanIntegration("None", ["#ia_sam_image", "#ia_sel_mask"]);
});
