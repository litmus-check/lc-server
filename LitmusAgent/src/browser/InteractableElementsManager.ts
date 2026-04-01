import { InteractableElement } from '../types/browser';
import { logger } from '../utils/logger';

export class InteractableElementsManager {
    private static instance: InteractableElementsManager;
    private elements: InteractableElement[] = [];

    private constructor() {}

    public static getInstance(): InteractableElementsManager {
        if (!InteractableElementsManager.instance) {
            InteractableElementsManager.instance = new InteractableElementsManager();
        }
        return InteractableElementsManager.instance;
    }

    public setElements(elements: InteractableElement[]): void {
        this.elements = elements;
        logger.info(`Set ${elements.length} interactable elements`);
    }

    public getElements(): InteractableElement[] {
        return this.elements;
    }

    public getElementById(id: number): InteractableElement | undefined {
        return this.elements.find(element => Number(element.id) === id);
    }

    public getElementsBySelector(selector: string): InteractableElement[] {
        return this.elements.filter(element => element.selector === selector);
    }

    public clearElements(): void {
        this.elements = [];
        logger.info('Cleared interactable elements');
    }

    public getVisibleElements(): InteractableElement[] {
        return this.elements.filter(element => element.isVisible);
    }

    public getEnabledElements(): InteractableElement[] {
        return this.elements.filter(element => element.isEnabled);
    }
} 