import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { DashboardComponent } from './dashboard.component';

describe('DashboardComponent', () => {
  it('offers quick actions from the overview', async () => {
    await TestBed.configureTestingModule({ imports: [DashboardComponent], providers: [provideRouter([])] }).compileComponents();
    const fixture = TestBed.createComponent(DashboardComponent);
    fixture.detectChanges();
    const content = fixture.nativeElement.textContent;
    expect(content).toContain('Tạo workspace mới');
    expect(content).toContain('Tải tài liệu lên');
    expect(content).toContain('Tạo chatbot');
    expect(content).toContain('Nhúng chatbot');
    expect(fixture.nativeElement.querySelector('a[href="/app/workspaces"]')).not.toBeNull();
  });
});
