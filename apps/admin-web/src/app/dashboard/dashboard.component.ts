import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
} from "@angular/core";
import { RouterLink } from "@angular/router";
import { NzCardModule } from "ng-zorro-antd/card";
import { NzIconModule, provideNzIconsPatch } from "ng-zorro-antd/icon";
import { NzTagModule } from "ng-zorro-antd/tag";
import {
  CloudServerOutline,
  DatabaseOutline,
  FileTextOutline,
  MessageOutline,
} from "@ant-design/icons-angular/icons";
import { catchError, forkJoin, map, of, switchMap } from "rxjs";

import { session } from "../core/api-auth.interceptor";
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
  createdAt: string;
}

@Component({
  selector: "raghub-dashboard",
  imports: [NzCardModule, NzIconModule, NzTagModule, RouterLink],
  providers: [
    provideNzIconsPatch([
      CloudServerOutline,
      DatabaseOutline,
      FileTextOutline,
      MessageOutline,
    ]),
  ],
  templateUrl: "./dashboard.component.html",
  styleUrl: "./dashboard.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent {
  protected readonly services = [
    {
      name: "PostgreSQL",
      role: "Dữ liệu và trạng thái xử lý",
      icon: "database",
    },
    { name: "Redis", role: "Hàng đợi tác vụ Celery", icon: "cloud-server" },
    {
      name: "Elasticsearch",
      role: "Tìm kiếm trong phạm vi tổ chức",
      icon: "database",
    },
    { name: "MinIO", role: "Lưu trữ tài liệu gốc", icon: "file-text" },
  ];
  protected readonly loading = signal(true);
  protected readonly error = signal("");
  protected readonly workspaces = signal<Workspace[]>([]);
  protected readonly documents = signal<
    (DocumentItem & { workspaceName: string })[]
  >([]);
  protected readonly bots = signal<(Chatbot & { workspaceName: string })[]>([]);
  protected readonly recent = computed<Activity[]>(() => {
    const docs: Activity[] = this.documents().map((doc) => ({
      kind: "document",
      title: `Tài liệu ${doc.name} đã được thêm`,
      subtitle: doc.workspaceName,
      createdAt: doc.created_at,
    }));
    const bots: Activity[] = this.bots().map((bot) => ({
      kind: "chatbot",
      title: `Chatbot ${bot.name} ${bot.published ? "đã được xuất bản" : "đã được tạo"}`,
      subtitle: bot.workspaceName,
      createdAt: bot.created_at,
    }));
    return [...docs, ...bots]
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .slice(0, 5);
  });
  private readonly api = inject(RaghubApiService);

  constructor() {
    this.api
      .organizations()
      .pipe(
        switchMap((orgs) => {
          const orgId = session.organizationId ?? orgs[0]?.id ?? "";
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
                    docs.map((doc) => ({ ...doc, workspaceName: ws.name })),
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
            docs as (DocumentItem & { workspaceName: string })[],
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
