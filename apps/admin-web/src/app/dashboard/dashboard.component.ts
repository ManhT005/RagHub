import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
} from "@angular/core";
import { DatePipe } from "@angular/common";
import { FormsModule } from "@angular/forms";
import { NzDatePickerModule } from "ng-zorro-antd/date-picker";
import { NzSelectModule } from "ng-zorro-antd/select";
import { NzTableModule } from "ng-zorro-antd/table";
import { NzTagModule } from "ng-zorro-antd/tag";
import { catchError, forkJoin, map, of, switchMap } from "rxjs";

import { session } from "../core/api-auth.interceptor";
import { consoleOrganization } from "../core/console-organization";
import {
  Chatbot,
  DocumentItem,
  RaghubApiService,
  Workspace,
} from "../core/raghub-api.service";

interface Activity {
  kind: "document" | "chatbot";
  title: string;
  subtitle: string;
  workspaceId: string;
  createdAt: string;
}

@Component({
  selector: "raghub-dashboard",
  imports: [
    DatePipe,
    FormsModule,
    NzDatePickerModule,
    NzSelectModule,
    NzTableModule,
    NzTagModule,
  ],
  templateUrl: "./dashboard.component.html",
  styleUrl: "./dashboard.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent {
  protected readonly loading = signal(true);
  protected readonly error = signal("");
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly selectedWorkspace = signal("");
  protected readonly dateRange = signal<Date[] | null>(null);
  protected readonly pageSize = 10;
  protected readonly documents = signal<
    (DocumentItem & { workspaceId: string; workspaceName: string })[]
  >([]);
  protected readonly bots = signal<(Chatbot & { workspaceName: string })[]>([]);
  protected readonly activities = computed<Activity[]>(() => {
    const docs: Activity[] = this.documents().map((doc) => ({
      kind: "document",
      title: `Tài liệu ${doc.name} đã được thêm`,
      subtitle: doc.workspaceName,
      workspaceId: doc.workspaceId,
      createdAt: doc.created_at,
    }));
    const bots: Activity[] = this.bots().map((bot) => ({
      kind: "chatbot",
      title: `Chatbot ${bot.name} ${bot.published ? "đã được xuất bản" : "đã được tạo"}`,
      subtitle: bot.workspaceName,
      workspaceId: bot.workspace_id,
      createdAt: bot.created_at,
    }));
    return [...docs, ...bots].sort((a, b) =>
      b.createdAt.localeCompare(a.createdAt),
    );
  });
  protected readonly filteredActivities = computed<Activity[]>(() => {
    const workspaceId = this.selectedWorkspace();
    const range = this.dateRange();
    const from = range?.[0] ? new Date(range[0]) : null;
    const to = range?.[1] ? new Date(range[1]) : null;
    from?.setHours(0, 0, 0, 0);
    to?.setHours(23, 59, 59, 999);

    return this.activities().filter((activity) => {
      if (workspaceId && activity.workspaceId !== workspaceId) return false;
      const createdAt = new Date(activity.createdAt).getTime();
      if (from && createdAt < from.getTime()) return false;
      if (to && createdAt > to.getTime()) return false;
      return true;
    });
  });
  private readonly api = inject(RaghubApiService);

  constructor() {
    this.api
      .organizations()
      .pipe(
        switchMap((orgs) => {
          const orgId = consoleOrganization(orgs)?.id ?? "";
          if (!orgId)
            return of({ workspaces: [] as Workspace[], docs: [], bots: [] });
          session.organizationId = orgId;
          return this.api.workspaces().pipe(
            switchMap((items) => {
              if (!items.length)
                return of({ workspaces: items, docs: [], bots: [] });
              const docReqs = items.map((ws) =>
                this.api.documents(ws.id).pipe(
                  map((docs) =>
                    docs.map((doc) => ({
                      ...doc,
                      workspaceId: ws.id,
                      workspaceName: ws.name,
                    })),
                  ),
                  catchError(() => of([])),
                ),
              );
              const botReqs = items.map((ws) =>
                this.api.chatbots(ws.id).pipe(
                  map((bots) =>
                    bots.map((bot) => ({ ...bot, workspaceName: ws.name })),
                  ),
                  catchError(() => of([])),
                ),
              );
              return forkJoin({
                docs: forkJoin(docReqs).pipe(map((groups) => groups.flat())),
                bots: forkJoin(botReqs).pipe(map((groups) => groups.flat())),
              }).pipe(
                map(({ docs, bots }) => ({ workspaces: items, docs, bots })),
              );
            }),
            catchError(() =>
              of({ workspaces: [] as Workspace[], docs: [], bots: [] }),
            ),
          );
        }),
      )
      .subscribe({
        next: ({ workspaces, docs, bots }) => {
          this.workspaces.set(workspaces);
          this.documents.set(
            docs as (DocumentItem & {
              workspaceId: string;
              workspaceName: string;
            })[],
          );
          this.bots.set(bots as (Chatbot & { workspaceName: string })[]);
          this.loading.set(false);
        },
        error: () => {
          this.error.set(
            "Không thể tải số liệu tổng quan. Hãy đăng nhập và chọn tổ chức.",
          );
          this.loading.set(false);
        },
      });
  }
}
