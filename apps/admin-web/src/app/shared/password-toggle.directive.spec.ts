import { Component } from "@angular/core";
import { TestBed } from "@angular/core/testing";
import { FormsModule } from "@angular/forms";
import { PasswordToggleDirective } from "./password-toggle.directive";

@Component({ imports: [FormsModule, PasswordToggleDirective], template: `
  <form (ngSubmit)="submissions = submissions + 1"><label>Mật khẩu<input type="password" name="password" autocomplete="new-password" [(ngModel)]="password" [disabled]="disabled"></label>
  <label>Nhập lại<input type="password" name="confirmation" [(ngModel)]="confirmation"></label><button type="submit">Lưu</button></form>` })
class FormHost { password = ""; confirmation = ""; disabled = false; submissions = 0; }

describe("password visibility", () => {
  it("toggles each input independently without losing values or submitting the form", async () => {
    const fixture = TestBed.createComponent(FormHost);
    fixture.detectChanges(); await fixture.whenStable();
    const inputs = fixture.nativeElement.querySelectorAll('input') as NodeListOf<HTMLInputElement>;
    const buttons = fixture.nativeElement.querySelectorAll('.rh-password-toggle') as NodeListOf<HTMLButtonElement>;
    inputs[0].value = "my-password"; inputs[0].dispatchEvent(new Event('input'));
    fixture.detectChanges(); await fixture.whenStable();
    expect(inputs[0].type).toBe("password");
    expect(buttons[0].getAttribute('aria-label')).toBe("Hiện mật khẩu");
    buttons[0].click(); fixture.detectChanges();
    expect(inputs[0].type).toBe("text");
    expect(inputs[1].type).toBe("password");
    expect(inputs[0].value).toBe("my-password");
    expect(inputs[0].autocomplete).toBe("new-password");
    expect(fixture.componentInstance.password).toBe("my-password");
    expect(fixture.componentInstance.submissions).toBe(0);
    expect(buttons[0].getAttribute('aria-pressed')).toBe("true");
    buttons[0].click();
    expect(inputs[0].type).toBe("password");
    expect(buttons[0].getAttribute('aria-controls')).toBe(inputs[0].id);
  });
  it("follows disabled input state and cleans up generated controls", async () => {
    const fixture = TestBed.createComponent(FormHost);
    fixture.detectChanges(); await fixture.whenStable();
    fixture.componentInstance.disabled = true;
    fixture.detectChanges(); await fixture.whenStable();
    await Promise.resolve();
    expect(fixture.nativeElement.querySelector('.rh-password-toggle').disabled).toBe(true);
    fixture.destroy();
    expect(fixture.nativeElement.querySelector('.rh-password-toggle')).toBeNull();
  });
});
