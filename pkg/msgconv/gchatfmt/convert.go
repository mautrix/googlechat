package gchatfmt

import (
	"context"
	"fmt"
	"html"
	"log"
	"sort"
	"strings"

	pb "google.golang.org/protobuf/proto"
	"maunium.net/go/mautrix/bridgev2"
	"maunium.net/go/mautrix/bridgev2/networkid"
	"maunium.net/go/mautrix/event"

	"go.mau.fi/mautrix-googlechat/pkg/gchatmeow"
	"go.mau.fi/mautrix-googlechat/pkg/gchatmeow/proto"
)

func Parse(ctx context.Context, portal *bridgev2.Portal,
	msg *proto.Message) *event.MessageEventContent {
	if msg.TextBody == "" {
		return nil
	}

	content := &event.MessageEventContent{
		MsgType: event.MsgText,
		Body:    msg.TextBody,
	}

	if len(msg.Annotations) > 0 {
		utf16Str := gchatmeow.NewUTF16String(msg.TextBody)
		bodyHtml, err := annotationsToMatrix(ctx, portal, utf16Str, msg.Annotations, 0, 0)
		if err != nil {
			log.Printf("[msgconv:gchatfmt] error: annotation conversion error: %#v", err)
		}

		if bodyHtml != "" {
			content.Format = event.FormatHTML
			content.FormattedBody = bodyHtml
		}
	}

	return content
}

func normalizeAnnotations(annotations []*proto.Annotation) []*proto.Annotation {
	if len(annotations) == 0 {
		return annotations
	}

	sort.Slice(annotations, func(i, j int) bool {
		if annotations[i].StartIndex == annotations[j].StartIndex {
			return annotations[i].Length > annotations[j].Length
		}
		return annotations[i].StartIndex < annotations[j].StartIndex
	})

	i := 0
	insertAnnotations := make([]*proto.Annotation, 0)

	for i < len(annotations) {
		cur := annotations[i]
		end := cur.StartIndex + cur.Length

		foundBreak := false
		for i2, annotation := range annotations[i+1:] {
			if annotation.StartIndex >= end {
				newAnnotations := make([]*proto.Annotation, 0, len(annotations)+len(insertAnnotations))
				newAnnotations = append(newAnnotations, annotations[:i+1+i2]...)
				newAnnotations = append(newAnnotations, insertAnnotations...)
				newAnnotations = append(newAnnotations, annotations[i+1+i2:]...)
				annotations = newAnnotations
				insertAnnotations = make([]*proto.Annotation, 0)
				i += 1 + i2
				foundBreak = true
				break
			} else if annotation.StartIndex+annotation.Length > end {
				annotationCopy := pb.Clone(annotation).(*proto.Annotation)
				annotation.Length = end - annotation.StartIndex
				annotationCopy.StartIndex = annotationCopy.StartIndex + annotation.Length
				annotationCopy.Length = annotationCopy.Length - annotation.Length
				insertAnnotations = append(insertAnnotations, annotationCopy)
			}
		}

		if !foundBreak {
			i++
		}
	}

	if len(insertAnnotations) > 0 {
		annotations = append(annotations, insertAnnotations...)
	}

	return annotations
}

func escape(text gchatmeow.UTF16String) string {
	return html.EscapeString(text.String())
}

func annotationsToMatrix(
	ctx context.Context,
	portal *bridgev2.Portal,
	text gchatmeow.UTF16String,
	annotations []*proto.Annotation,
	offset int32,
	length int32,
) (string, error) {
	if len(annotations) == 0 {
		return escape(text), nil
	}

	textLen := len(text)
	if length == 0 {
		length = int32(textLen)
	}

	bodyHtml := strings.Builder{}
	var lastOffset int32 = 0

	annotations = normalizeAnnotations(annotations)

	for i, annotation := range annotations {
		if annotation.StartIndex >= offset+length {
			break
		} else if annotation.ChipRenderType != proto.Annotation_DO_NOT_RENDER {
			// Annotations with "RENDER" type are rendered separately
			continue
		}

		// Overlapping annotations should be removed by NormalizeAnnotations
		if annotation.StartIndex+annotation.Length > offset+length {
			return "", fmt.Errorf("annotation extends beyond text bounds")
		}

		relativeOffset := annotation.StartIndex - offset
		if relativeOffset > lastOffset {
			bodyHtml.WriteString(escape(text[lastOffset:relativeOffset]))
		} else if relativeOffset < lastOffset {
			continue
		}

		skipEntity := false
		entityText, err := annotationsToMatrix(
			ctx,
			portal,
			text[relativeOffset:relativeOffset+annotation.Length],
			annotations[i+1:],
			annotation.StartIndex,
			annotation.Length,
		)
		if err != nil {
			return "", err
		}

		if annotation.GetFormatMetadata() != nil {
			switch annotation.GetFormatMetadata().FormatType {
			case proto.FormatMetadata_HIDDEN:
				// Don't append the text
			case proto.FormatMetadata_BOLD:
				fmt.Fprintf(&bodyHtml, "<strong>%s</strong>", entityText)
			case proto.FormatMetadata_ITALIC:
				fmt.Fprintf(&bodyHtml, "<em>%s</em>", entityText)
			case proto.FormatMetadata_UNDERLINE:
				fmt.Fprintf(&bodyHtml, "<u>%s</u>", entityText)
			case proto.FormatMetadata_STRIKE:
				fmt.Fprintf(&bodyHtml, "<del>%s</del>", entityText)
			case proto.FormatMetadata_MONOSPACE:
				fmt.Fprintf(&bodyHtml, "<code>%s</code>", entityText)
			case proto.FormatMetadata_MONOSPACE_BLOCK:
				fmt.Fprintf(&bodyHtml, "<pre><code>%s</code></pre>", entityText)
			case proto.FormatMetadata_FONT_COLOR:
				rgbInt := annotation.GetFormatMetadata().GetFontColor()
				color := (rgbInt + 1<<31) & 0xFFFFFF
				fmt.Fprintf(&bodyHtml, "<font color='#%06x'>%s</font>", color, entityText)
			case proto.FormatMetadata_BULLETED_LIST_ITEM:
				fmt.Fprintf(&bodyHtml, "<li>%s</li>", entityText)
			case proto.FormatMetadata_BULLETED_LIST:
				fmt.Fprintf(&bodyHtml, "<ul>%s</ul>", entityText)
			default:
				skipEntity = true
			}
		} else if annotation.GetUrlMetadata() != nil {
			fmt.Fprintf(&bodyHtml, "<a href='%s'>%s</a>", annotation.GetUrlMetadata().Url.Url, entityText)
		} else if annotation.GetUserMentionMetadata() != nil {
			if annotation.GetUserMentionMetadata().Type == proto.UserMentionMetadata_MENTION_ALL {
				bodyHtml.WriteString("@room")
			} else {
				gcid := annotation.GetUserMentionMetadata().Id.Id
				dmPortals, err := portal.Bridge.GetDMPortalsWith(ctx, networkid.UserID(gcid))
				if err != nil {
					return "", err
				}

				if len(dmPortals) != 0 {
					fmt.Fprintf(&bodyHtml,
						`<a href="%s">%s</a>`,
						dmPortals[0].MXID.URI().MatrixToURL(),
						dmPortals[0].Name,
					)
				} else {
					userLogin := portal.Bridge.GetCachedUserLoginByID(networkid.UserLoginID(gcid))
					if userLogin != nil {
						fmt.Fprintf(&bodyHtml,
							`<a href="%s">%s</a>`,
							userLogin.UserMXID.URI().MatrixToURL(),
							entityText,
						)

					} else {
						bodyHtml.WriteString(entityText)
					}
				}
			}
		} else {
			skipEntity = true
		}

		if skipEntity {
			lastOffset = relativeOffset
		} else {
			lastOffset = relativeOffset + annotation.Length
		}
	}

	bodyHtml.WriteString(escape(text[lastOffset:]))
	return bodyHtml.String(), nil
}
