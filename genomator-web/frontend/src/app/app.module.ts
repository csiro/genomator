import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';

import { MatTabsModule } from '@angular/material/tabs';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { NavBarComponent } from './nav-bar/nav-bar.component'; // Import the NavBarComponent
import { FooterComponent } from './footer/footer.component';
import { FontAwesomeModule } from '@fortawesome/angular-fontawesome'; // Import the FooterComponent
import { ToastrModule } from 'ngx-toastr';
import { HIGHLIGHT_OPTIONS } from 'ngx-highlightjs';

@NgModule({
  declarations: [AppComponent, NavBarComponent, FooterComponent],
  imports: [
    BrowserModule,
    AppRoutingModule,
    MatTabsModule,
    BrowserAnimationsModule,
    FontAwesomeModule,
    ToastrModule.forRoot(),
  ],
  providers: [
    {
      provide: HIGHLIGHT_OPTIONS,
      useValue: {
        coreLibraryLoader: () => import('highlight.js/lib/core'),
        languages: {
          python: () => import('highlight.js/lib/languages/python'),
        },
      },
    },
  ],
  bootstrap: [AppComponent],
})
export class AppModule {}
