import {
  AfterViewInit,
  Component,
  ElementRef,
  OnInit,
  ViewChild,
} from '@angular/core';
import { faPlayCircle } from '@fortawesome/free-regular-svg-icons';

declare var particlesJS: any;
declare var bootstrap: any;

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['app.component.css'],
})
export class AppComponent implements OnInit, AfterViewInit {
  @ViewChild('particles', { static: true }) particles: ElementRef | undefined;
  faPlayCircle = faPlayCircle;

  ngOnInit(): void {
    this.invokeParticles();
  }

  ngAfterViewInit(): void {
    const tooltipTriggerList = document.querySelectorAll(
      '[data-bs-toggle="tooltip"]'
    );
    const tooltipList = [...tooltipTriggerList].map(
      (tooltipTriggerEl) => new bootstrap.Tooltip(tooltipTriggerEl)
    );
  }

  invokeParticles(): void {
    particlesJS.load('particles-js', 'assets/particles.json', () => {
      console.log('Particles.js config loaded');
    });
  }

  toggleAnimation(): void {
    if (!this.particles) {
      return;
    }
    const div = this.particles.nativeElement as HTMLDivElement;
    if (div.style.display === 'none') {
      div.style.display = 'block';
    } else {
      div.style.display = 'none';
    }
  }

  title = 'genomator-web';
}
