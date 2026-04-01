import { LLMAgent } from '../LLM';
import { MessageManager } from '../MessageManager';
import { AgentOutput } from '../AgentOutput';
import { logger } from '../../utils/logger';
import { describe, expect, it, beforeAll } from '@jest/globals';
import { HumanMessage } from '@langchain/core/messages';
import { BrowserAgent } from '../../browser/BrowserAgent';
const fs = require('fs');
const path = require('path');

describe('Prompt Actions Tests', () => {
    let llm: LLMAgent;
    let messageManager: MessageManager;
    const interactable_elements = {
        "currentUrl": "https://parabank.parasoft.com/parabank/admin.htm",
        "elementsCount": 45,
        "elements": [
          {
            "id": "1",
            "selector": "//*[@id=\"topPanel\"]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "admin.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 202,
              "y": 0,
              "width": 0,
              "height": 0
            },
            "isVisible": false,
            "isEnabled": true,
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "2",
            "selector": "//*[@id=\"topPanel\"]/a[2]",
            "tagName": "A",
            "attributes": {
              "href": "index.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 202,
              "y": 0,
              "width": 0,
              "height": 0
            },
            "isVisible": false,
            "isEnabled": true,
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "3",
            "selector": "//*[@id=\"headerPanel\"]/ul[1]/li[2]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "about.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 293,
              "y": 99,
              "width": 137,
              "height": 22
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "About Us",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "4",
            "selector": "//*[@id=\"headerPanel\"]/ul[1]/li[3]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "services.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 293,
              "y": 122,
              "width": 137,
              "height": 22
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Services",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "5",
            "selector": "//*[@id=\"headerPanel\"]/ul[1]/li[4]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "http://www.parasoft.com/jsp/products.jsp"
            },
            "boundingBox": {
              "x": 293,
              "y": 145,
              "width": 137,
              "height": 22
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Products",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "6",
            "selector": "//*[@id=\"headerPanel\"]/ul[1]/li[5]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "http://www.parasoft.com/jsp/pr/contacts.jsp"
            },
            "boundingBox": {
              "x": 293,
              "y": 168,
              "width": 137,
              "height": 22
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Locations",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "7",
            "selector": "//*[@id=\"headerPanel\"]/ul[1]/li[6]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "admin.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 293,
              "y": 191,
              "width": 137,
              "height": 22
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Admin Page",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "8",
            "selector": "//*[@id=\"headerPanel\"]/ul[2]/li[1]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "index.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 821,
              "y": 175,
              "width": 42,
              "height": 45
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "home",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "9",
            "selector": "//*[@id=\"headerPanel\"]/ul[2]/li[2]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "about.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 875,
              "y": 175,
              "width": 42,
              "height": 45
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "about",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "10",
            "selector": "//*[@id=\"headerPanel\"]/ul[2]/li[3]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "contact.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 929,
              "y": 175,
              "width": 42,
              "height": 45
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "contact",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "11",
            "selector": "input[name=\"username\"]",
            "tagName": "INPUT",
            "attributes": {
              "type": "text",
              "class": "input",
              "name": "username"
            },
            "boundingBox": {
              "x": 293,
              "y": 305,
              "width": 146,
              "height": 18
            },
            "isVisible": true,
            "isEnabled": true,
            "name": "username",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "12",
            "selector": "input[name=\"password\"]",
            "tagName": "INPUT",
            "attributes": {
              "type": "password",
              "class": "input",
              "name": "password"
            },
            "boundingBox": {
              "x": 293,
              "y": 353,
              "width": 146,
              "height": 18
            },
            "isVisible": true,
            "isEnabled": true,
            "name": "password",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "13",
            "selector": "//*[@id=\"loginPanel\"]/form[1]/div[3]/input[1]",
            "tagName": "INPUT",
            "attributes": {
              "type": "submit",
              "class": "button",
              "value": "Log In"
            },
            "boundingBox": {
              "x": 293,
              "y": 382.1328125,
              "width": 66.4453125,
              "height": 19
            },
            "isVisible": true,
            "isEnabled": true,
            "value": "Log In",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "14",
            "selector": "//*[@id=\"loginPanel\"]/p[1]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "lookup.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 293,
              "y": 413.1328125,
              "width": 100.453125,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Forgot login info?",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "15",
            "selector": "//*[@id=\"loginPanel\"]/p[2]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "register.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 293,
              "y": 432.1328125,
              "width": 48.4140625,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Register",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "16",
            "selector": "button[name=\"action\"]",
            "tagName": "BUTTON",
            "attributes": {
              "type": "submit",
              "class": "button",
              "name": "action",
              "value": "INIT"
            },
            "boundingBox": {
              "x": 520.0703125,
              "y": 343.1328125,
              "width": 82.5546875,
              "height": 19
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Initialize",
            "value": "INIT",
            "name": "action",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "17",
            "selector": "button[name=\"action\"]",
            "tagName": "BUTTON",
            "attributes": {
              "type": "submit",
              "class": "button",
              "name": "action",
              "value": "CLEAN"
            },
            "boundingBox": {
              "x": 649.375,
              "y": 343.1328125,
              "width": 66.4453125,
              "height": 19
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Clean",
            "value": "CLEAN",
            "name": "action",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "18",
            "selector": "input[name=\"shutdown\"]",
            "tagName": "INPUT",
            "attributes": {
              "type": "hidden",
              "name": "shutdown",
              "value": "true"
            },
            "boundingBox": {
              "x": 0,
              "y": 0,
              "width": 0,
              "height": 0
            },
            "isVisible": false,
            "isEnabled": true,
            "value": "true",
            "name": "shutdown",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "19",
            "selector": "//*[@id=\"rightPanel\"]/table[1]/tbody[1]/tr[1]/td[2]/form[1]/table[1]/tbody[1]/tr[1]/td[3]/input[1]",
            "tagName": "INPUT",
            "attributes": {
              "type": "submit",
              "class": "button",
              "value": "Shutdown"
            },
            "boundingBox": {
              "x": 877.1015625,
              "y": 343.1328125,
              "width": 90.8828125,
              "height": 19
            },
            "isVisible": true,
            "isEnabled": true,
            "value": "Shutdown",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "20",
            "selector": "#accessMode1",
            "tagName": "INPUT",
            "attributes": {
              "id": "accessMode1",
              "name": "accessMode",
              "class": "input",
              "type": "radio",
              "value": "soap"
            },
            "boundingBox": {
              "x": 522.25,
              "y": 425.1328125,
              "width": 200,
              "height": 13
            },
            "isVisible": true,
            "isEnabled": true,
            "value": "soap",
            "name": "accessMode",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "21",
            "selector": "#accessMode2",
            "tagName": "INPUT",
            "attributes": {
              "id": "accessMode2",
              "name": "accessMode",
              "class": "input",
              "type": "radio",
              "value": "restxml"
            },
            "boundingBox": {
              "x": 764.75,
              "y": 425.1328125,
              "width": 200,
              "height": 13
            },
            "isVisible": true,
            "isEnabled": true,
            "value": "restxml",
            "name": "accessMode",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "22",
            "selector": "#accessMode3",
            "tagName": "INPUT",
            "attributes": {
              "id": "accessMode3",
              "name": "accessMode",
              "class": "input",
              "type": "radio",
              "value": "restjson",
              "checked": "checked"
            },
            "boundingBox": {
              "x": 522.25,
              "y": 486.1328125,
              "width": 200,
              "height": 13
            },
            "isVisible": true,
            "isEnabled": true,
            "value": "restjson",
            "name": "accessMode",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "23",
            "selector": "#accessMode4",
            "tagName": "INPUT",
            "attributes": {
              "id": "accessMode4",
              "name": "accessMode",
              "class": "input",
              "type": "radio",
              "value": "jdbc"
            },
            "boundingBox": {
              "x": 764.75,
              "y": 486.1328125,
              "width": 200,
              "height": 13
            },
            "isVisible": true,
            "isEnabled": true,
            "value": "jdbc",
            "name": "accessMode",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "24",
            "selector": "//*[@id=\"adminForm\"]/table[2]/tbody[1]/tr[1]/td[1]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "services/ParaBank;jsessionid=E631D5A356B3758C4C69B257587B30B7?wsdl"
            },
            "boundingBox": {
              "x": 616.6953125,
              "y": 650.1328125,
              "width": 37.078125,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "WSDL",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "25",
            "selector": "//*[@id=\"adminForm\"]/table[2]/tbody[1]/tr[1]/td[1]/a[2]",
            "tagName": "A",
            "attributes": {
              "href": "services/bank;jsessionid=E631D5A356B3758C4C69B257587B30B7?_wadl&_type=xml"
            },
            "boundingBox": {
              "x": 664.375,
              "y": 650.1328125,
              "width": 36.6015625,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "WADL",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "26",
            "selector": "//*[@id=\"adminForm\"]/table[2]/tbody[1]/tr[1]/td[1]/a[3]",
            "tagName": "A",
            "attributes": {
              "href": "api-docs/index.html;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 711.578125,
              "y": 650.1328125,
              "width": 52.7578125,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "OpenAPI",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "27",
            "selector": "#soapEndpoint",
            "tagName": "INPUT",
            "attributes": {
              "id": "soapEndpoint",
              "name": "soapEndpoint",
              "class": "inputLarge",
              "type": "text",
              "value": ""
            },
            "boundingBox": {
              "x": 585,
              "y": 682.6328125,
              "width": 406,
              "height": 18
            },
            "isVisible": true,
            "isEnabled": true,
            "name": "soapEndpoint",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "28",
            "selector": "#restEndpoint",
            "tagName": "INPUT",
            "attributes": {
              "id": "restEndpoint",
              "name": "restEndpoint",
              "class": "inputLarge",
              "type": "text",
              "value": ""
            },
            "boundingBox": {
              "x": 585,
              "y": 725.6328125,
              "width": 406,
              "height": 18
            },
            "isVisible": true,
            "isEnabled": true,
            "name": "restEndpoint",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "29",
            "selector": "//*[@id=\"adminForm\"]/table[2]/tbody[1]/tr[6]/td[1]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "services/LoanProcessor;jsessionid=E631D5A356B3758C4C69B257587B30B7?wsdl"
            },
            "boundingBox": {
              "x": 651.359375,
              "y": 830.1328125,
              "width": 37.078125,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "WSDL",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "30",
            "selector": "#endpoint",
            "tagName": "INPUT",
            "attributes": {
              "id": "endpoint",
              "name": "endpoint",
              "class": "inputLarge",
              "type": "text",
              "value": ""
            },
            "boundingBox": {
              "x": 585,
              "y": 853.1328125,
              "width": 406,
              "height": 18
            },
            "isVisible": true,
            "isEnabled": true,
            "name": "endpoint",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "31",
            "selector": "#initialBalance",
            "tagName": "INPUT",
            "attributes": {
              "id": "initialBalance",
              "name": "initialBalance",
              "class": "input",
              "type": "text",
              "value": "515.50"
            },
            "boundingBox": {
              "x": 619.8125,
              "y": 950.1328125,
              "width": 206,
              "height": 18
            },
            "isVisible": true,
            "isEnabled": true,
            "value": "515.50",
            "name": "initialBalance",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "32",
            "selector": "#minimumBalance",
            "tagName": "INPUT",
            "attributes": {
              "id": "minimumBalance",
              "name": "minimumBalance",
              "class": "input",
              "type": "text",
              "value": "100.00"
            },
            "boundingBox": {
              "x": 619.8125,
              "y": 974.1328125,
              "width": 206,
              "height": 18
            },
            "isVisible": true,
            "isEnabled": true,
            "value": "100.00",
            "name": "minimumBalance",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "33",
            "selector": "#loanProvider",
            "tagName": "SELECT",
            "attributes": {
              "id": "loanProvider",
              "name": "loanProvider",
              "class": "input"
            },
            "boundingBox": {
              "x": 619.8125,
              "y": 1044.1328125,
              "width": 140,
              "height": 17.5
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "JMS\n\t\t\t\t\t\n\t\t\t\t\t\t\n\t\t\t\t\t\tWeb Service\n\t\t\t\t\t\n\t\t\t\t\t\t\n\t\t\t\t\t\tLocal",
            "value": "ws",
            "name": "loanProvider",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "34",
            "selector": "#loanProcessor",
            "tagName": "SELECT",
            "attributes": {
              "id": "loanProcessor",
              "name": "loanProcessor",
              "class": "input"
            },
            "boundingBox": {
              "x": 619.8125,
              "y": 1068.1328125,
              "width": 140,
              "height": 17.5
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Available Funds\n\t\t\t\t\t\n\t\t\t\t\t\t\n\t\t\t\t\t\tDown Payment\n\t\t\t\t\t\n\t\t\t\t\t\t\n\t\t\t\t\t\tCombined",
            "value": "funds",
            "name": "loanProcessor",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "35",
            "selector": "#loanProcessorThreshold",
            "tagName": "INPUT",
            "attributes": {
              "id": "loanProcessorThreshold",
              "name": "loanProcessorThreshold",
              "class": "inputSmall",
              "type": "text",
              "value": "20"
            },
            "boundingBox": {
              "x": 619.8125,
              "y": 1092.1328125,
              "width": 56,
              "height": 18
            },
            "isVisible": true,
            "isEnabled": true,
            "value": "20",
            "name": "loanProcessorThreshold",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "36",
            "selector": "//*[@id=\"adminForm\"]/input[1]",
            "tagName": "INPUT",
            "attributes": {
              "type": "submit",
              "class": "button",
              "value": "Submit"
            },
            "boundingBox": {
              "x": 488,
              "y": 1138.265625,
              "width": 70.3359375,
              "height": 19
            },
            "isVisible": true,
            "isEnabled": true,
            "value": "Submit",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": false
          },
          {
            "id": "37",
            "selector": "//*[@id=\"footerPanel\"]/ul[1]/li[1]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "index.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 336,
              "y": 1195.765625,
              "width": 53.3671875,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Home",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "38",
            "selector": "//*[@id=\"footerPanel\"]/ul[1]/li[2]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "about.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 396.1875,
              "y": 1195.765625,
              "width": 71.7578125,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "About Us",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "39",
            "selector": "//*[@id=\"footerPanel\"]/ul[1]/li[3]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "services.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 474.765625,
              "y": 1195.765625,
              "width": 67.265625,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Services",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "40",
            "selector": "//*[@id=\"footerPanel\"]/ul[1]/li[4]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "http://www.parasoft.com/jsp/products.jsp"
            },
            "boundingBox": {
              "x": 548.8515625,
              "y": 1195.765625,
              "width": 69.8671875,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Products",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "41",
            "selector": "//*[@id=\"footerPanel\"]/ul[1]/li[5]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "http://www.parasoft.com/jsp/pr/contacts.jsp"
            },
            "boundingBox": {
              "x": 625.5390625,
              "y": 1195.765625,
              "width": 75.03125,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Locations",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "42",
            "selector": "//*[@id=\"footerPanel\"]/ul[1]/li[6]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "http://forums.parasoft.com/"
            },
            "boundingBox": {
              "x": 707.390625,
              "y": 1195.765625,
              "width": 56.75,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Forum",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "43",
            "selector": "//*[@id=\"footerPanel\"]/ul[1]/li[7]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "sitemap.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 770.9609375,
              "y": 1195.765625,
              "width": 69.421875,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Site Map",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "44",
            "selector": "//*[@id=\"footerPanel\"]/ul[1]/li[8]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "contact.htm;jsessionid=E631D5A356B3758C4C69B257587B30B7"
            },
            "boundingBox": {
              "x": 847.203125,
              "y": 1195.765625,
              "width": 83.0390625,
              "height": 15
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "Contact Us",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          },
          {
            "id": "45",
            "selector": "//*[@id=\"footerPanel\"]/ul[2]/li[2]/a[1]",
            "tagName": "A",
            "attributes": {
              "href": "http://www.parasoft.com/",
              "target": "_blank"
            },
            "boundingBox": {
              "x": 390.84375,
              "y": 1242.265625,
              "width": 84.2734375,
              "height": 20
            },
            "isVisible": true,
            "isEnabled": true,
            "text": "www.parasoft.com",
            "isInCookieBanner": false,
            "hasClickHandler": false,
            "hasAriaProps": false,
            "isContentEditable": false,
            "isDraggable": true
          }
        ]
      };

    beforeAll(() => {
        llm = new LLMAgent();
    });

    describe('Click Action Tests', () => {
        it('should handle click action correctly', async () => {
            messageManager = new MessageManager();
            
            messageManager.createInitMessage("ai_click");


            // Add the instructions to the message from the front
            messageManager.addUserMessage(JSON.stringify({
                action: "ai_click",
                prompt: "Click on 'Submit' button"
            }), true);

            // Read image file and convert to base64
            const imagePath = path.join('test2.png'); // Adjust path as needed
            const imageBuffer = fs.readFileSync(imagePath);
            const base64Image = imageBuffer.toString('base64');
            const image = `data:image/png;base64,${base64Image}`;


            messageManager.addUserMessage([
                  {
                    type: "image_url",
                    image_url: {
                      url: image,
                    },
                  },
                  {
                    type: "text",
                    text: JSON.stringify(interactable_elements),
                  },
                ],
            )

            logger.info("Click Action Messages:", messageManager.getMessages());
            



            const response = await llm.invokeWithTools(messageManager.getMessages());
            logger.info('Click Action Response:' + JSON.stringify(response, null, 2));
            
            // expect(response).toBeInstanceOf(AgentOutput);
            expect(response.Actions).toBeDefined();
            expect(response.Actions[0].type).toBe('ai_click');
            expect(response.Reasoning).toBeDefined();
        }, 100000);
    });

    describe('Hover Action Tests', () => {
        it('should handle hover action correctly', async () => {
            messageManager = new MessageManager();
            
            messageManager.createInitMessage("ai_hover");

            // Add the instructions to the message from the front
            messageManager.addUserMessage(JSON.stringify({
                action: "ai_hover",
                prompt: "Hover over 'Clean' button"
            }), true);

            // Read image file and convert to base64
            const imagePath = path.join('test2.png'); // Adjust path as needed
            const imageBuffer = fs.readFileSync(imagePath);
            const base64Image = imageBuffer.toString('base64');
            const image = `data:image/png;base64,${base64Image}`;

            messageManager.addUserMessage([
                {
                    type: "image_url",
                    image_url: {
                        url: image,
                    },
                },
                {
                    type: "text",
                    text: JSON.stringify(interactable_elements),
                },
            ]);

            logger.info("Hover Action Messages:", messageManager.getMessages());

            const response = await llm.invokeWithTools(messageManager.getMessages());
            logger.info('Hover Action Response:' + JSON.stringify(response, null, 2));
            
            expect(response.Actions).toBeDefined();
            expect(response.Actions[0].type).toBe('ai_hover');
            expect(response.Reasoning).toBeDefined();
        }, 100000);
    });

    describe('Input Action Tests', () => {
        it('should handle input action correctly', async () => {
            messageManager = new MessageManager();
            
            messageManager.createInitMessage("ai_input");

            // Add the instructions to the message from the front
            messageManager.addUserMessage(JSON.stringify({
                action: "ai_input",
                prompt: "Init. Balance",
            }), true);

            // Read image file and convert to base64
            const imagePath = path.join('test2.png'); // Adjust path as needed
            const imageBuffer = fs.readFileSync(imagePath);
            const base64Image = imageBuffer.toString('base64');
            const image = `data:image/png;base64,${base64Image}`;

            messageManager.addUserMessage([
                {
                    type: "image_url",
                    image_url: {
                        url: image,
                    },
                },
                {
                    type: "text",
                    text: JSON.stringify(interactable_elements),
                },
            ]);

            logger.info("Input Action Messages:", messageManager.getMessages());

            const response = await llm.invokeWithTools(messageManager.getMessages());
            logger.info('Input Action Response:' + JSON.stringify(response, null, 2));
            
            expect(response.Actions).toBeDefined();
            expect(response.Actions[0].type).toBe('ai_input');
            expect(response.Reasoning).toBeDefined();
        }, 100000);
    });

    describe('Select Action Tests', () => {
        it('should handle select action correctly', async () => {
            messageManager = new MessageManager();
            
            messageManager.createInitMessage("ai_select");

            // Add the instructions to the message from the front
            messageManager.addUserMessage(JSON.stringify({
                action: "ai_select",
                prompt: "Select Loan Provider",
            }), true);

            // Read image file and convert to base64
            const imagePath = path.join('test2.png'); // Adjust path as needed
            const imageBuffer = fs.readFileSync(imagePath);
            const base64Image = imageBuffer.toString('base64');
            const image = `data:image/png;base64,${base64Image}`;

            messageManager.addUserMessage([
                {
                    type: "image_url",
                    image_url: {
                        url: image,
                    },
                },
                {
                    type: "text",
                    text: JSON.stringify(interactable_elements),
                },
            ]);

            const response = await llm.invokeWithTools(messageManager.getMessages());
            logger.info('Select Action Response:' + JSON.stringify(response, null, 2));
            
            expect(response.Actions).toBeDefined();
            expect(response.Actions[0].type).toBe('ai_select');
            expect(response.Reasoning).toBeDefined();
        }, 100000);
    });

    describe('Select Action Tests2', () => {
        it('should handle select action correctly', async () => {
            messageManager = new MessageManager();
            
            messageManager.createInitMessage("ai_select");

            // Add the instructions to the message from the front
            messageManager.addUserMessage(JSON.stringify({
                action: "ai_select",
                prompt: "SOAP radio button",
            }), true);

            // Read image file and convert to base64
            const imagePath = path.join('test2.png'); // Adjust path as needed
            const imageBuffer = fs.readFileSync(imagePath);
            const base64Image = imageBuffer.toString('base64');
            const image = `data:image/png;base64,${base64Image}`;

            messageManager.addUserMessage([
                {
                    type: "image_url",
                    image_url: {
                        url: image,
                    },
                },
                {
                    type: "text",
                    text: JSON.stringify(interactable_elements),
                },
            ]);

            const response = await llm.invokeWithTools(messageManager.getMessages());
            logger.info('Select Action Response:' + JSON.stringify(response, null, 2));
            
            expect(response.Actions).toBeDefined();
            expect(response.Actions[0].type).toBe('ai_select');
            expect(response.Reasoning).toBeDefined();
        }, 100000);
    });

    describe('Verify Action Tests', () => {
        it('should handle verify action correctly', async () => {
            messageManager = new MessageManager();
            
            messageManager.createInitMessage("ai_verify");

            // Get page content using BrowserAgent with tracing disabled
            const browserAgent = new BrowserAgent({
                config: {
                    tracePath: undefined, // Disable tracing
                    headless: true,
                    viewport: { width: 1280, height: 720 },
                    timeout: 30000,
                    retryAttempts: 3,
                    waitBetweenActions: 1000,
                    useBrowserbase: false,
                    cdpUrl: undefined,
                    screenshotBeforeAction: false,
                    screenshotAfterAction: false
                }
            });
            
            try {
                await browserAgent.initialize();
                
                // Navigate to the test page
                await browserAgent.executeAction({
                    type: 'go_to_url',
                    url: 'https://parabank.parasoft.com/parabank/admin.htm'
                });

                // Wait for page to load
                await new Promise(resolve => setTimeout(resolve, 2000));

                const pageContent = await browserAgent.getPageContent();

                // Add the instructions to the message from the front
                messageManager.addUserMessage(JSON.stringify({
                    action: "ai_verify",
                    prompt: "Check if login button is present or not",
                    extracted_content: pageContent,
                    framework: "playwright"
                }), true);

                // Read image file and convert to base64
                const imagePath = path.join('test2.png'); // Adjust path as needed
                const imageBuffer = fs.readFileSync(imagePath);
                const base64Image = imageBuffer.toString('base64');
                const image = `data:image/png;base64,${base64Image}`;

                messageManager.addUserMessage([
                    {
                        type: "image_url",
                        image_url: {
                            url: image,
                        },
                    },
                    {
                        type: "text",
                        text: JSON.stringify(interactable_elements),
                    },
                ]);

                const response = await llm.invokeWithTools(messageManager.getMessages());
                logger.info('Verify Action Response:' + JSON.stringify(response, null, 2));
                
                expect(response.Actions).toBeDefined();
                expect(response.Actions[0].type).toBe('ai_verify');
                expect(response.Reasoning).toBeDefined();
            } catch (error) {
                logger.error('Test failed:', error);
                throw error;
            } finally {
                await browserAgent.cleanup();
            }
        }, 100000);
    });

    // describe('Error Handling Tests', () => {
    //     it('should handle invalid element gracefully', async () => {
    //         messageManager = new MessageManager();
    //         messageManager.addUserMessage(JSON.stringify({
    //             action: "ai_click",
    //             prompt: "Click on non-existent button"
    //         }));

    //         const response = await llm.invoke(messageManager.getMessages());
    //         console.log('Error Handling Response:', JSON.stringify(response, null, 2));
            
    //         expect(response).toBeInstanceOf(AgentOutput);
    //         expect(response.Actions).toBeDefined();
    //         expect(response.Warning).toBeDefined();
    //     });

    //     it('should handle parsing errors gracefully', async () => {
    //         messageManager = new MessageManager();
    //         messageManager.addUserMessage("Invalid JSON format");

    //         const response = await llm.invoke(messageManager.getMessages());
    //         console.log('Parsing Error Response:', JSON.stringify(response, null, 2));
            
    //         expect(response).toBeInstanceOf(AgentOutput);
    //         expect(response.ParsingError).toBe(true);
    //         expect(response.Warning).toBeDefined();
    //     });
    // });
}); 