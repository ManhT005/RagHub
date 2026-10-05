import {
  Directive,
  TemplateRef,
  ViewContainerRef,
  effect,
  inject,
  input,
} from "@angular/core";
import { WorkspaceContextStore } from "../workspace-context/workspace-context.store";
import { WorkspacePermission } from "./permission.types";

@Directive({ selector: "[appCan]" })
export class CanDirective {
  readonly appCan = input.required<WorkspacePermission>();
  private readonly context = inject(WorkspaceContextStore);
  private readonly template = inject(TemplateRef);
  private readonly container = inject(ViewContainerRef);
  private visible = false;
  constructor() {
    effect(() => {
      const allowed = this.context.can(this.appCan());
      if (allowed === this.visible) return;
      this.container.clear();
      if (allowed) this.container.createEmbeddedView(this.template);
      this.visible = allowed;
    });
  }
}
